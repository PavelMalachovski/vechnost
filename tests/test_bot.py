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
        """The application is built from the token in settings.

        Patching os.environ cannot do this: `settings` is a module-level
        Settings() built at import, so by the time a test runs the value is
        already read. The old form asserted "test_token" and therefore passed
        or failed on whatever the developer had exported.
        """
        with patch.object(settings, "telegram_bot_token", "424242:REAL-LOOKING"):
            app = create_application()

        assert isinstance(app, Application)
        assert app.bot.token == "424242:REAL-LOOKING"

    def test_create_application_rejects_a_token_that_is_not_one(self):
        """A missing token stops being a ValueError from our own code and
        becomes python-telegram-bot refusing to build a Bot around it."""
        with patch.object(settings, "telegram_bot_token", ""):
            with pytest.raises(InvalidToken):
                create_application()

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"})
    @patch('vechnost_bot.bot.Application.run_polling')
    def test_run_bot_success(self, mock_run_polling):
        """Test successful bot run."""
        mock_run_polling.return_value = AsyncMock()

        # Should not raise any exceptions
        run_bot()

        mock_run_polling.assert_called_once()

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"})
    @patch('vechnost_bot.bot.Application.run_polling')
    def test_run_bot_exception_handling(self, mock_run_polling):
        """Test bot run with exception handling."""
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
