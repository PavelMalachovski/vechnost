"""Tests for bot application setup and configuration."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from telegram.ext import Application

from vechnost_bot.bot import create_application, run_bot, setup_logging
from vechnost_bot.config import Settings


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

    # run_bot() opens with initialize_redis_sync(), which tries to auto-start
    # a real Redis. Unpatched, these two hang for as long as that takes to
    # give up — and whether they hang at all depended on what an earlier test
    # in the same process had already done to the Redis singletons, which is
    # exactly the kind of order dependence that breaks under -n auto.
    @patch('vechnost_bot.bot.cleanup_redis_sync')
    @patch('vechnost_bot.bot.initialize_redis_sync', return_value=False)
    @patch('vechnost_bot.bot.Application.run_polling')
    def test_run_bot_success(self, mock_run_polling, mock_init_redis, mock_cleanup):
        """Test successful bot run."""
        mock_run_polling.return_value = AsyncMock()

        # Should not raise any exceptions
        run_bot()

        mock_run_polling.assert_called_once()
        mock_init_redis.assert_called_once()

    @patch('vechnost_bot.bot.cleanup_redis_sync')
    @patch('vechnost_bot.bot.initialize_redis_sync', return_value=False)
    @patch('vechnost_bot.bot.Application.run_polling')
    def test_run_bot_exception_handling(self, mock_run_polling, mock_init_redis, mock_cleanup):
        """A failing poll is re-raised, and Redis is cleaned up on the way out."""
        mock_run_polling.side_effect = Exception("Test error")

        with pytest.raises(Exception, match="Test error"):
            run_bot()

        mock_cleanup.assert_called_once()


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
        "ENVIRONMENT": "production"
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
