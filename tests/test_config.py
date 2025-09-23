"""Tests for configuration management."""

import pytest
import os
from unittest.mock import patch, MagicMock

from vechnost_bot.config import Settings, create_bot, get_log_level, get_chat_id


class TestSettings:
    """Test Settings configuration."""

    def test_settings_defaults(self):
        """Test default settings values."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"}):
            settings = Settings()

            assert settings.telegram_bot_token == "test_token"
            assert settings.log_level == "INFO"
            assert settings.environment == "development"
            assert str(settings.redis_url) == "redis://localhost:6379/0"
            assert settings.redis_db == 0
            assert settings.chat_id is None
            assert settings.sentry_dsn is None
            assert settings.max_connections == 20
            assert settings.session_ttl == 3600

    def test_settings_from_env(self):
        """Test settings loaded from environment variables."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "prod_token",
            "LOG_LEVEL": "DEBUG",
            "ENVIRONMENT": "production",
            "REDIS_URL": "redis://prod-redis:6379",
            "REDIS_DB": "1",
            "CHAT_ID": "12345",
            "SENTRY_DSN": "https://sentry.io/project",
            "MAX_CONNECTIONS": "50",
            "SESSION_TTL": "7200"
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "prod_token"
            assert settings.log_level == "DEBUG"
            assert settings.environment == "production"
            assert str(settings.redis_url) == "redis://prod-redis:6379"
            assert settings.redis_db == 1
            assert settings.chat_id == "12345"
            assert settings.sentry_dsn == "https://sentry.io/project"
            assert settings.max_connections == 50
            assert settings.session_ttl == 7200

    def test_settings_validation(self):
        """Test settings validation."""
        # Test missing required token
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                Settings()

    def test_redis_dsn_validation(self):
        """Test Redis DSN validation."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "REDIS_URL": "invalid-url"
        }):
            with pytest.raises(ValueError):
                Settings()

    def test_numeric_validation(self):
        """Test numeric field validation."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "REDIS_DB": "invalid_number"
        }):
            with pytest.raises(ValueError):
                Settings()


class TestConfigFunctions:
    """Test configuration utility functions."""

    @patch('vechnost_bot.config.settings')
    def test_create_bot(self, mock_settings):
        """Test bot creation."""
        mock_settings.telegram_bot_token = "test_token"

        bot = create_bot()

        assert bot.token == "test_token"

    @patch('vechnost_bot.config.settings')
    def test_get_log_level(self, mock_settings):
        """Test log level retrieval."""
        mock_settings.log_level = "DEBUG"

        level = get_log_level()

        assert level == "DEBUG"

    @patch('vechnost_bot.config.settings')
    def test_get_chat_id(self, mock_settings):
        """Test chat ID retrieval."""
        mock_settings.chat_id = "12345"

        chat_id = get_chat_id()

        assert chat_id == "12345"

    @patch('vechnost_bot.config.settings')
    def test_get_chat_id_none(self, mock_settings):
        """Test chat ID retrieval when None."""
        mock_settings.chat_id = None

        chat_id = get_chat_id()

        assert chat_id is None


class TestSettingsIntegration:
    """Test settings integration with other components."""

    def test_settings_with_prefix(self):
        """Test settings with environment prefix."""
        env_vars = {
            "VECHNOST_TELEGRAM_BOT_TOKEN": "prefixed_token",
            "VECHNOST_LOG_LEVEL": "WARNING",
            "VECHNOST_REDIS_URL": "redis://prefixed-redis:6379"
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "prefixed_token"
            assert settings.log_level == "WARNING"
            assert str(settings.redis_url) == "redis://prefixed-redis:6379"

    def test_settings_case_insensitive(self):
        """Test case insensitive environment variables."""
        env_vars = {
            "telegram_bot_token": "lowercase_token",
            "LOG_LEVEL": "ERROR",
            "environment": "staging"
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "lowercase_token"
            assert settings.log_level == "ERROR"
            assert settings.environment == "staging"

    def test_settings_validation_alias(self):
        """Test validation alias for telegram token."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "alias_token"
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "alias_token"


class TestSettingsPerformance:
    """Test settings performance characteristics."""

    def test_settings_creation_speed(self):
        """Test settings creation speed."""
        import time

        env_vars = {
            "TELEGRAM_BOT_TOKEN": "perf_token",
            "LOG_LEVEL": "INFO",
            "REDIS_URL": "redis://localhost:6379"
        }

        with patch.dict(os.environ, env_vars):
            start_time = time.time()
            settings = Settings()
            end_time = time.time()

            # Should be fast (less than 100ms)
            assert (end_time - start_time) < 0.1
            assert settings.telegram_bot_token == "perf_token"

    def test_settings_memory_usage(self):
        """Test settings memory usage."""
        import sys

        env_vars = {
            "TELEGRAM_BOT_TOKEN": "memory_token",
            "LOG_LEVEL": "INFO"
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            # Settings object should be lightweight
            size = sys.getsizeof(settings)
            assert size < 1000  # Less than 1KB


class TestSettingsErrorHandling:
    """Test settings error handling."""

    def test_invalid_redis_url(self):
        """Test invalid Redis URL handling."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "REDIS_URL": "not-a-valid-redis-url"
        }

        with patch.dict(os.environ, env_vars):
            with pytest.raises(ValueError):
                Settings()

    def test_invalid_numeric_values(self):
        """Test invalid numeric values."""
        test_cases = [
            ("REDIS_DB", "not_a_number"),
            ("MAX_CONNECTIONS", "invalid"),
            ("SESSION_TTL", "also_invalid")
        ]

        for env_var, invalid_value in test_cases:
            env_vars = {
                "TELEGRAM_BOT_TOKEN": "test_token",
                env_var: invalid_value
            }

            with patch.dict(os.environ, env_vars):
                with pytest.raises(ValueError):
                    Settings()

    def test_missing_required_field(self):
        """Test missing required field handling."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="telegram_bot_token"):
                Settings()
