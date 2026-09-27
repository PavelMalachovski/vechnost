"""What only PostgreSQL shows: the database production runs on.

Every other suite runs on SQLite, which accepted an untyped NULL where
PostgreSQL refuses one, has no ALTER COLUMN, and ignores row locks. So the
startup backfill failed on every production start and no test noticed
(backend audit B-01), and a database built by `alembic upgrade head` could
not take a lifetime purchase (B-05).

These run when POSTGRES_TEST_URL names a server - CI starts one, see
`.github/workflows/e2e.yml` - and are skipped with a reason otherwise. Each
test gets a database of its own, created and dropped around it.
"""

import asyncio
import logging
import os
import secrets
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings

pytestmark = pytest.mark.postgres

ADMIN_URL = os.environ.get("POSTGRES_TEST_URL", "")
REPO = Path(__file__).parent.parent


def _sync(url: str) -> str:
    return url.replace("+asyncpg", "+psycopg2")


@pytest.fixture
def pg_url() -> Iterator[str]:
    """A fresh, empty database on the server POSTGRES_TEST_URL names."""
    if not ADMIN_URL:
        pytest.skip("POSTGRES_TEST_URL is not set (CI sets it; see tests/test_postgres.py)")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    name = f"vechnost_pg_{secrets.token_hex(4)}"
    admin = create_engine(_sync(ADMIN_URL), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _run(url: str, coro_factory):
    """Run app code against `url` with the app's own engine."""
    async def go():
        try:
            return await coro_factory()
        finally:
            await database.close_db()

    with (
        patch.object(settings, "database_url", url),
        patch.object(settings, "enable_payment", True),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        return asyncio.run(go())


def test_every_startup_step_succeeds_on_postgres(pg_url: str, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="vechnost_bot.payments.database")
    _run(pg_url, database.create_tables)
    _run(pg_url, database.create_tables)  # and again, as on the next restart
    assert "failed" not in caplog.text, caplog.text


def test_the_backfill_serves_legacy_customers_on_postgres(pg_url: str) -> None:
    from sqlalchemy import func, select

    from vechnost_bot.payments.models import Subscription, User
    from vechnost_bot.payments.repositories import PaymentRepository, UserRepository
    from vechnost_bot.payments.services import user_has_access

    cutover = datetime.fromisoformat(database.ACCESS_FROM_PAYMENTS_CUTOVER)

    async def seed() -> None:
        await database.create_tables()
        for tg_id, event, when in (
            (920_001, "new_digital_product", cutover - timedelta(days=40)),
            (920_002, "new_digital_product", cutover + timedelta(days=2)),
            (920_003, "chargeback", cutover + timedelta(days=4)),
        ):
            async with database.get_db() as session:
                user = await UserRepository.create_or_update(session, tg_id)
                payment = await PaymentRepository.create(
                    session, provider="tribute", event_name=event, user_id=user.id,
                    telegram_user_id=tg_id, amount=100, currency="rub",
                    raw_body={"name": event}, signature="pg", body_sha256=f"pg-{tg_id}",
                )
                payment.created_at = when

    async def restart_and_read() -> tuple[bool, bool, bool, int]:
        await database.create_tables()
        await database.create_tables()
        async with database.get_db() as session:
            rows = (await session.execute(
                select(func.count()).select_from(Subscription).join(User)
                .where(User.telegram_user_id == 920_001)
            )).scalar_one()
        return (
            await user_has_access(920_001),
            await user_has_access(920_002),
            await user_has_access(920_003),
            int(rows),
        )

    _run(pg_url, seed)
    legacy, gift, chargeback, rows = _run(pg_url, restart_and_read)
    assert legacy is True, "the customer the backfill exists for has access on PostgreSQL"
    assert rows == 1
    assert gift is False and chargeback is False


def test_alembic_builds_a_database_that_takes_a_lifetime_purchase(pg_url: str) -> None:
    """`alembic upgrade head` on PostgreSQL: it used to fail on the async URL
    (MissingGreenlet), then on the untyped NULL, rolling back to no tables;
    and the schema it built refused a subscription without an expiry."""
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    from alembic import command

    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "alembic"))
    with patch.object(settings, "database_url", pg_url):
        command.upgrade(config, "head")

    engine = create_engine(_sync(pg_url))
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("subscriptions")}
        assert columns["expires_at"]["nullable"] is True
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (telegram_user_id, created_at) "
                "VALUES (930001, CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "INSERT INTO subscriptions (user_id, subscription_id, period, status, "
                "expires_at, last_event_at) SELECT id, 0, 'lifetime', 'active', NULL, "
                "CURRENT_TIMESTAMP FROM users WHERE telegram_user_id = 930001"
            ))
    finally:
        engine.dispose()


def test_a_stray_not_null_is_released_at_startup(pg_url: str) -> None:
    """A database that already has the constraint gets it dropped on start."""
    from sqlalchemy import create_engine, inspect, text

    _run(pg_url, database.create_tables)
    engine = create_engine(_sync(pg_url))
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE subscriptions ALTER COLUMN expires_at SET NOT NULL"))
        _run(pg_url, database.create_tables)
        columns = {c["name"]: c for c in inspect(engine).get_columns("subscriptions")}
        assert columns["expires_at"]["nullable"] is True
    finally:
        engine.dispose()


def test_rejected_deliveries_are_kept_and_released_on_postgres(pg_url: str) -> None:
    """The release step renames a hash with `||` and matches with LIKE: both
    have to hold on the database production runs, and twice in a row."""
    from sqlalchemy import select

    from vechnost_bot.payments.models import WebhookEvent
    from vechnost_bot.payments.repositories import WebhookEventRepository

    async def seed() -> None:
        await database.create_tables()
        async with database.get_db() as session:
            for sha, status in (("pg-stuck", 401), ("pg-fine", 200)):
                await WebhookEventRepository.create(
                    session, name="new_digital_product", sent_at=datetime.utcnow(),
                    body_sha256=sha, status_code=status,
                )

    async def restart_twice_and_read() -> list[tuple[str, int]]:
        await database.create_tables()
        await database.create_tables()
        async with database.get_db() as session:
            found = (await session.execute(select(WebhookEvent))).scalars().all()
            return sorted((row.body_sha256, row.status_code) for row in found)

    _run(pg_url, seed)
    assert _run(pg_url, restart_twice_and_read) == [
        ("pg-fine", 200), (database.RELEASED_PREFIX + "pg-stuck", 401),
    ]


def test_the_heartbeat_round_trips_on_postgres(pg_url: str) -> None:
    """The bot writes a naive UTC timestamp and the web process subtracts it
    from its own clock: both halves have to hold on the database production
    runs, and a second beat must update the row rather than collide."""
    from vechnost_bot import heartbeat

    async def beat_twice_and_check() -> tuple[bool, dict]:
        await heartbeat.beat(at=heartbeat.utcnow() - timedelta(minutes=2))
        await heartbeat.beat()
        return await heartbeat.deep_status()

    healthy, checks = _run(pg_url, beat_twice_and_check)
    assert healthy, checks
    assert checks["bot_heartbeat_age_s"] < 60

    async def stale() -> tuple[bool, dict]:
        return await heartbeat.deep_status(now=heartbeat.utcnow() + timedelta(hours=1))

    healthy, checks = _run(pg_url, stale)
    assert not healthy and checks["bot"] == "stale"


def test_the_payment_columns_reach_an_existing_database_on_postgres(pg_url: str) -> None:
    """A database made before the event key, the purchase link and the
    revocation mark got them: the startup step adds the columns and their
    unique indexes, in SQL PostgreSQL accepts, and a second start changes
    nothing."""
    from sqlalchemy import create_engine, inspect, text

    _run(pg_url, database.create_tables)
    engine = create_engine(_sync(pg_url))
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE webhook_events DROP COLUMN event_key"))
            conn.execute(text("ALTER TABLE certificates DROP COLUMN purchase_id"))
            conn.execute(text("ALTER TABLE certificates DROP COLUMN revoked_at"))
        _run(pg_url, database.create_tables)
        _run(pg_url, database.create_tables)
        inspector = inspect(engine)
        for table, column, index in (
            ("webhook_events", "event_key", "uq_webhook_events_event_key"),
            ("certificates", "purchase_id", "uq_certificates_purchase_id"),
        ):
            assert column in {c["name"] for c in inspector.get_columns(table)}
            [found] = [i for i in inspector.get_indexes(table) if i["name"] == index]
            assert found["unique"] and found["column_names"] == [column]
        revoked_at = {c["name"]: c for c in inspector.get_columns("certificates")}["revoked_at"]
        assert str(revoked_at["type"]) == "TIMESTAMP" and revoked_at["nullable"] is True
    finally:
        engine.dispose()


def _schema(sync_url: str) -> dict[str, dict[str, tuple[str, bool]]]:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(sync_url)
    try:
        inspector = inspect(engine)
        return {
            table: {c["name"]: (str(c["type"]), bool(c["nullable"]))
                    for c in inspector.get_columns(table)}
            for table in inspector.get_table_names() if table != "alembic_version"
        }
    finally:
        engine.dispose()


def test_alembic_and_create_all_build_the_same_schema(pg_url: str) -> None:
    """Two ways of building one schema must not disagree.

    Deploys run create_all (plus the startup steps); the docs send a manual
    setup through `alembic upgrade head`. Where the two drifted - a NOT NULL
    here, a server default there - the drift went unnoticed until a payment
    failed, so any column one has and the other lacks, or types or
    nullability that differ, fail here first.
    """
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from alembic import command

    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "alembic"))
    with patch.object(settings, "database_url", pg_url):
        command.upgrade(config, "head")
    by_alembic = _schema(_sync(pg_url))

    other = f"vechnost_pg_{secrets.token_hex(4)}"
    admin = create_engine(_sync(ADMIN_URL), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{other}"'))
    try:
        other_url = make_url(pg_url).set(database=other).render_as_string(hide_password=False)
        _run(other_url, database.create_tables)
        by_create_all = _schema(_sync(other_url))
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{other}" WITH (FORCE)'))
        admin.dispose()

    assert by_alembic == by_create_all
