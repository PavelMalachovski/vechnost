"""Fixtures for the two-user suites: a server, and a way to see what happened.

`server` is the app under test. By default it is the FastAPI app in-process
behind Starlette's TestClient, on a throwaway SQLite file, with payments ON
and a fake Telegram that records every push. With `E2E_BASE_URL` set it is a
live server over real HTTP instead (CI runs one on PostgreSQL); scenarios
that need in-process powers — the fake Telegram, the bot — are marked
`inprocess_only` and skip themselves there. `E2E_DATABASE_URL` points the
in-process app at another database, e.g. a local PostgreSQL.

When a scenario fails, the report carries the transcript: every request each
player made and what came back, in order.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import httpx
import pytest

LIVE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    server = getattr(item, "funcargs", {}).get("server")
    if server is not None and server.transcript.exchanges:
        report.sections.append(("two-user transcript", server.transcript.render()))


def _inprocess_server(tmp_path: Any) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    import vechnost_bot.payments.database as database
    from vechnost_bot import compat_notify
    from vechnost_bot.config import settings
    from vechnost_bot.payments import gifts, grant_notify, partner_notify
    from vechnost_bot.payments.web import app

    from .fake_telegram import FakeTelegram
    from .harness import (
        E2E_BOT_USERNAME,
        E2E_TRIBUTE_KEY,
        E2E_WEBAPP_URL,
        Server,
    )

    db_url = os.environ.get("E2E_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}"
    telegram = FakeTelegram(E2E_BOT_USERNAME)
    overrides: dict[str, Any] = {
        "database_url": db_url,
        # Payments on, so every access check and the initData validation run.
        "enable_payment": True,
        "tribute_api_key": E2E_TRIBUTE_KEY,
        "webhook_secret": None,
        "tribute_payment_url": "https://tribute.invalid/pay",
        "referral_payment_url": None,
        "gift_product_id": None,
        "gift_payment_url": None,
        "admin_ids": None,
        # One proxy in front, as on Railway: each player's X-Forwarded-For
        # is their own address, so the throttle budgets them separately.
        "trusted_proxy_hops": 1,
        "bot_username": E2E_BOT_USERNAME,
        "webapp_url": E2E_WEBAPP_URL,
        "webapp_short_name": None,
        "webapp_main_app": False,
        "cors_allow_origins": None,
        "allowed_hosts": None,
    }
    with ExitStack() as stack:
        for name, value in overrides.items():
            stack.enter_context(patch.object(settings, name, value))
        stack.enter_context(patch.object(database, "engine", None))
        stack.enter_context(patch.object(database, "async_session_maker", None))
        stack.enter_context(patch.object(database, "_tables_created", False))
        # Pushes go to the fake Telegram, where a scenario can read them.
        stack.enter_context(
            patch.object(compat_notify, "_bot", lambda: telegram.bot(settings.telegram_bot_token))
        )
        stack.enter_context(
            patch.object(grant_notify, "_bot", lambda: telegram.bot(settings.telegram_bot_token))
        )
        stack.enter_context(
            patch.object(partner_notify, "_bot", lambda: telegram.bot(settings.telegram_bot_token))
        )
        stack.enter_context(patch.object(gifts, "Bot", lambda token: telegram.bot(token)))
        client = stack.enter_context(TestClient(app, base_url="http://e2e.test"))
        server = Server(
            client, live=False, bot_token=settings.telegram_bot_token, telegram=telegram
        )
        server.portal = client.portal
        yield server


@pytest.fixture
def server(tmp_path: Any, request: pytest.FixtureRequest) -> Iterator[Any]:
    """The app under test, with payments on, reached as two real users would."""
    from .harness import Server

    if LIVE_URL:
        if request.node.get_closest_marker("inprocess_only"):
            pytest.skip("needs the in-process server (fake Telegram / the bot)")
        token = os.environ.get("E2E_BOT_TOKEN") or os.environ["TELEGRAM_BOT_TOKEN"]
        with httpx.Client(base_url=LIVE_URL, timeout=30) as http:
            yield Server(http, live=True, bot_token=token)
        return
    if request.node.get_closest_marker("live_only"):
        pytest.skip("needs a live server over real HTTP: set E2E_BASE_URL")
    yield from _inprocess_server(tmp_path)


@pytest.fixture
def bot(server: Any) -> Iterator[Any]:
    """The real bot application, fed by two users, on the web app's loop."""
    from vechnost_bot import bot as bot_module
    from vechnost_bot.config import settings

    from .fake_telegram import BotDriver

    fake_bot = server.telegram.bot(settings.telegram_bot_token)
    with patch.object(bot_module, "create_bot", lambda: fake_bot):
        application = bot_module.create_application()
    # Handlers registered with block=False (/delete_me, the broadcast) run as
    # background tasks in production, so a send to thousands does not hold
    # up everyone else. Here a scenario reads the outcome right after the
    # tap, so every update is handled to completion before the next.
    for handlers in application.handlers.values():
        for handler in handlers:
            handler.block = True
    server.portal.call(application.initialize)
    try:
        yield BotDriver(server, application)
    finally:
        server.portal.call(application.shutdown)
