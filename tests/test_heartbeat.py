"""The bot's heartbeat, and the deep health check that reads it.

Production runs the web server and the bot as two processes, and `/health`
- Railway's healthcheck - only ever proved the first was up. A bot that had
died, or was alive with its event loop stuck, looked exactly as healthy as a
working one. The bot now writes a row every minute and `/health/deep`
answers 503 once it is older than a few minutes, or when the database does
not answer at all.
"""

import asyncio
import importlib.util
import logging
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from telegram.ext import Application

import vechnost_bot.payments.database as database
from vechnost_bot import heartbeat
from vechnost_bot.config import settings
from vechnost_bot.payments.models import Heartbeat
from vechnost_bot.payments.web import app

REPO = Path(__file__).parent.parent


@pytest.fixture
def db(tmp_path):
    """A database of this test's own, disposed of before its loop is gone."""
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'heartbeat.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield
        asyncio.run(database.close_db())


def _run(coro_factory):
    async def go():
        try:
            return await coro_factory()
        finally:
            await database.close_db()

    return asyncio.run(go())


def _beat(ago: timedelta = timedelta(0)) -> None:
    _run(lambda: heartbeat.beat(at=heartbeat.utcnow() - ago))


def _deep(client: TestClient):
    response = client.get("/health/deep")
    return response.status_code, response.json()


@pytest.fixture
def client(db):
    return TestClient(app)


def test_a_bot_that_beat_a_moment_ago_is_healthy(client):
    _beat(timedelta(seconds=30))

    status, body = _deep(client)

    assert status == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["bot"] == "ok"
    assert 25 <= body["checks"]["bot_heartbeat_age_s"] <= 90


def test_a_bot_that_stopped_beating_is_a_503(client):
    _beat(heartbeat.STALE_AFTER + timedelta(minutes=1))

    status, body = _deep(client)

    assert status == 503
    assert body["status"] == "unhealthy"
    assert body["checks"]["bot"] == "stale"


def test_a_bot_that_never_beat_is_a_503(client):
    status, body = _deep(client)

    assert status == 503
    assert body["checks"] == {"database": "ok", "bot": "no heartbeat yet"}


def test_a_database_that_does_not_answer_is_a_503_that_names_no_host(client):
    """The check answers anyone, so it says what failed and nothing more."""
    boom = OperationalError("SELECT 1", {}, Exception("could not reach db.internal:5432"))
    with patch.object(heartbeat, "get_db", side_effect=boom):
        response = client.get("/health/deep")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "error: OperationalError"
    assert "db.internal" not in response.text


def test_the_railway_healthcheck_stays_light(client):
    """`/health` must not depend on the database or the bot: a blip in
    either would make Railway refuse a deploy, or recycle a web process
    that serves fine."""
    with patch.object(heartbeat, "get_db", side_effect=RuntimeError("database down")):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_the_answer_is_never_cached(client):
    _beat()
    assert client.get("/health/deep").headers["cache-control"] == "no-store"


def test_a_beat_rewrites_one_row(db):
    old = heartbeat.utcnow() - timedelta(minutes=3)
    _run(lambda: heartbeat.beat(at=old))
    _run(heartbeat.beat)

    async def read():
        async with database.get_db() as session:
            count = await session.scalar(select(func.count()).select_from(Heartbeat))
            last = await session.scalar(select(Heartbeat.beat_at))
        return count, last

    count, last = _run(read)
    assert count == 1
    assert last > old


async def test_the_job_only_logs_when_the_database_is_down(caplog):
    """An error here every minute would page nobody and bury everything else;
    reporting the database is `/health/deep`'s job."""
    caplog.set_level(logging.WARNING, logger="vechnost_bot.heartbeat")
    with patch.object(heartbeat, "beat", side_effect=RuntimeError("database down")):
        await heartbeat.heartbeat_job(None)

    assert "Heartbeat not written" in caplog.text


def test_register_heartbeat_beats_every_minute():
    application = Application.builder().token("1234567890:TEST_TOKEN_FOR_UNIT_TESTS").build()

    heartbeat.register_heartbeat(application)

    (job,) = application.job_queue.get_jobs_by_name("heartbeat")
    assert job.callback is heartbeat.heartbeat_job
    assert job.job.trigger.interval == heartbeat.INTERVAL


def test_the_bot_registers_its_heartbeat():
    """The wiring: without this line in bot.py the deep check is red forever."""
    from vechnost_bot.bot import create_application

    names = {job.name for job in create_application().job_queue.jobs()}

    assert "heartbeat" in names


def test_no_job_queue_is_survivable(caplog):
    class NoQueue:
        job_queue = None

    caplog.set_level(logging.WARNING, logger="vechnost_bot.heartbeat")
    heartbeat.register_heartbeat(NoQueue())  # type: ignore[arg-type]

    assert "no heartbeat" in caplog.text


def _smoke_module():
    """scripts/smoke_production.py, imported as a module.

    Registered in sys.modules before it runs: its dataclass resolves its
    annotations through the module it was defined in.
    """
    spec = importlib.util.spec_from_file_location(
        "smoke_production", REPO / "scripts" / "smoke_production.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {spec.name: module}):
        spec.loader.exec_module(module)
    return module


def test_the_smoke_checks_the_bot_only_when_asked(client):
    smoke = _smoke_module()

    default = {check.name for check in smoke.smoke(client, None)}
    assert "database and bot" not in default

    _beat()
    deep = {check.name: check for check in smoke.smoke(client, None, deep=True)}
    assert deep["database and bot"].ok, deep["database and bot"].detail


def test_the_deep_smoke_fails_on_a_silent_bot(client):
    smoke = _smoke_module()

    checks = {check.name: check for check in smoke.smoke(client, None, deep=True)}

    assert not checks["database and bot"].ok
    assert "no heartbeat yet" in checks["database and bot"].detail
