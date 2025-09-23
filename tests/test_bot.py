"""Tests for bot application setup and configuration."""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from telegram.ext import Application

from vechnost_bot.bot import create_application, run_bot, setup_logging
from vechnost_bot.config import Settings


class TestBotSetup:
    """Test bot application setup."""

    def test_setup_logging(self):
        """Test logging setup."""
        # Should not raise any exceptions
        setup_logging()

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_create_application_success(self):
        """Test successful application creation."""
        app = create_application()

        assert isinstance(app, Application)
        assert app.bot.token == "test_token"

    @patch.dict(os.environ, {}, clear=True)
    def test_create_application_missing_token(self):
        """Test application creation with missing token."""
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN environment variable is required"):
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
