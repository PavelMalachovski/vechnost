"""Tests for bot application setup and configuration."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import InvalidToken
from telegram.ext import Application

from vechnost_bot.bot import create_application, run_bot, setup_logging
from vechnost_bot.config import Settings, settings


class TestBotSetup:
    """Test bot application setup."""

    def test_setup_logging(self):
        """Test logging setup."""
        # Should not raise any exceptions
        setup_logging()

    def test_create_application_success(self):
        """The application is built on the configured token.

        Asserted against `settings` rather than a literal: settings are read
        once at import, so patching the environment inside the test changes
        nothing, and a literal would only be testing what the test runner
        happened to export.
        """
        from vechnost_bot.config import settings

        app = create_application()

        assert isinstance(app, Application)
        assert app.bot.token == settings.telegram_bot_token

    def test_the_sweep_and_the_nudge_survive_the_daily_card_being_off(self):
        """DAILY_CARD_ENABLED governs only the daily card itself.

        All three jobs used to be scheduled inside the daily-card branch, so
        turning the push off silently stopped the retention sweep — the one
        thing that ever deletes rooms and abandoned tests — and the stalled
        game nudge along with it.
        """
        from vechnost_bot.bot import daily_jobs

        with patch.object(settings, "daily_card_enabled", False):
            names = {job.name for job in daily_jobs()}
        assert names == {"retention_sweep", "steps69_nudge"}

    def test_the_daily_card_is_scheduled_when_enabled(self):
        from vechnost_bot.bot import daily_jobs

        with patch.object(settings, "daily_card_enabled", True):
            names = {job.name for job in daily_jobs()}
        assert names == {"daily_card", "steps69_nudge", "retention_sweep"}

    def test_the_daily_jobs_ride_one_tick_beside_the_heartbeat(self):
        """The three daily jobs are not JobQueue jobs any more: one tick a
        minute starts whichever is due, so a restart across a slot or in the
        middle of a run is caught up (see tests/test_jobs.py)."""
        app = create_application()
        names = {job.name for job in app.job_queue.jobs()}
        assert names == {"heartbeat", "scheduled_jobs"}

    def test_the_slots_are_the_ones_the_settings_name(self):
        from datetime import time

        from vechnost_bot.bot import daily_jobs

        with (
            patch.object(settings, "daily_card_enabled", True),
            patch.object(settings, "daily_card_hour_utc", 23),
        ):
            slots = {job.name: job.at for job in daily_jobs()}
        assert slots == {
            "daily_card": time(23),
            "steps69_nudge": time(0),  # an hour after the card, across midnight
            "retention_sweep": time(3, 30),
        }

    def test_updates_run_side_by_side_but_each_chat_in_order(self):
        from vechnost_bot.bot import CONCURRENT_UPDATES, PerChatUpdateProcessor

        app = create_application()
        assert isinstance(app.update_processor, PerChatUpdateProcessor)
        assert app.update_processor.max_concurrent_updates == CONCURRENT_UPDATES > 1

    def test_the_bot_has_a_pool_for_them(self):
        from vechnost_bot.config import BOT_API_CONNECTIONS, BOT_API_POOL_TIMEOUT

        request = create_application().bot.request
        pool = request._client_kwargs["limits"]
        assert pool.max_connections == BOT_API_CONNECTIONS >= 32
        assert request._client_kwargs["timeout"].pool == BOT_API_POOL_TIMEOUT

    def test_a_missing_token_is_refused_at_import_not_at_call(self):
        """There is no token check inside create_application, by design.

        Settings are constructed when `vechnost_bot.config` is imported, so a
        deployment with no token never reaches this function — it fails on
        import, with pydantic naming the variable. Clearing the environment
        here would prove nothing: the value is already read.
        """
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
                Settings()

    def test_create_application_rejects_a_token_that_is_not_one(self):
        """And an empty token that somehow got past import is refused too.

        A deployment that sets `TELEGRAM_BOT_TOKEN=` gets a Settings object
        that validates - the variable is present, it is just empty - so the
        refusal has to come from python-telegram-bot, at the point a Bot is
        built. It does, and it names the token.
        """
        with patch.object(settings, "telegram_bot_token", ""):
            with pytest.raises(InvalidToken):
                create_application()

    @patch('vechnost_bot.bot.Application.run_polling')
    def test_run_bot_success(self, mock_run_polling):
        """run_bot builds the application and polls, and starts nothing else.

        It used to open with a synchronous Redis auto-start, which these
        tests had to patch out or hang for as long as that took to give up.
        """
        mock_run_polling.return_value = AsyncMock()

        with patch("subprocess.Popen", side_effect=AssertionError("spawned a process")):
            run_bot()

        mock_run_polling.assert_called_once()

    @patch('vechnost_bot.bot.Application.run_polling')
    def test_run_bot_exception_handling(self, mock_run_polling):
        """A failing poll is re-raised."""
        mock_run_polling.side_effect = Exception("Test error")

        with pytest.raises(Exception, match="Test error"):
            run_bot()


class TestConfig:
    """Test configuration management."""

    def test_settings_defaults(self):
        """Test default settings values."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"}):
            settings = Settings()

            assert settings.telegram_bot_token == "test_token"
            assert settings.log_level == "INFO"
            assert settings.environment == "development"

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token",
        "LOG_LEVEL": "DEBUG",
        "ENVIRONMENT": "production",
        # Production refuses to start without these (tests/test_config.py).
        "DATABASE_URL": "postgresql+asyncpg://vechnost@db.internal:5432/vechnost",
        "ENABLE_PAYMENT": "false",
    })
    def test_settings_from_env(self):
        """Test settings from environment variables."""
        settings = Settings()

        assert settings.telegram_bot_token == "test_token"
        assert settings.log_level == "DEBUG"
        assert settings.environment == "production"

    @patch.dict(os.environ, {}, clear=True)
    def test_settings_validation(self):
        """Test settings validation."""
        with pytest.raises(ValueError):
            Settings()


# ---------------------------------------------------------------------------
# Updates side by side, one chat in order (audit I-06)
# ---------------------------------------------------------------------------

def _message_from(chat_id: int, update_id: int):
    from telegram import Update

    return Update.de_json({
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "P"},
            "text": "/start",
        },
    }, None)


async def test_one_chat_is_handled_in_order_and_other_chats_meanwhile():
    """Two taps of one person must not run at once - each handler reads,
    changes and saves that chat's session - but another person's tap must
    not wait behind them either."""
    import asyncio

    from vechnost_bot.bot import PerChatUpdateProcessor

    processor = PerChatUpdateProcessor(max_concurrent_updates=8)
    log: list[str] = []

    async def handle(name: str, pause: float) -> None:
        log.append(f"{name} start")
        await asyncio.sleep(pause)
        log.append(f"{name} end")

    await asyncio.gather(
        processor.process_update(_message_from(1, 1), handle("alice 1", 0.05)),
        processor.process_update(_message_from(1, 2), handle("alice 2", 0)),
        processor.process_update(_message_from(2, 3), handle("bob", 0)),
    )

    assert log.index("alice 1 end") < log.index("alice 2 start"), log
    assert log.index("bob end") < log.index("alice 1 end"), "bob waited for alice"
    assert processor._locks == {} and processor._waiting == {}, "locks are not kept"


async def test_an_update_without_a_chat_is_handled_as_it_comes():
    from vechnost_bot.bot import PerChatUpdateProcessor

    processor = PerChatUpdateProcessor()
    done: list[str] = []

    async def handle() -> None:
        done.append("ok")

    await processor.process_update(object(), handle())
    assert done == ["ok"]


async def test_a_failing_update_does_not_leave_its_chat_locked():
    from vechnost_bot.bot import PerChatUpdateProcessor

    processor = PerChatUpdateProcessor()

    async def boom() -> None:
        raise RuntimeError("handler failed")

    with pytest.raises(RuntimeError):
        await processor.process_update(_message_from(5, 1), boom())

    reached: list[bool] = []

    async def after() -> None:
        reached.append(True)

    await processor.process_update(_message_from(5, 2), after())
    assert reached == [True] and processor._locks == {}
