"""Tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from vechnost_bot.config import (
    ProductionConfigError,
    Settings,
    create_bot,
    get_chat_id,
    get_log_level,
    production_problems,
)


class TestSettings:
    """Test Settings configuration."""

    def test_settings_defaults(self):
        """Test default settings values."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"}):
            settings = Settings()

            assert settings.telegram_bot_token == "test_token"
            assert settings.log_level == "INFO"
            assert settings.environment == "development"
            # No Redis unless one is named: sessions stay in memory.
            assert settings.redis_url is None
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
            # What production has to say for itself; see TestProductionSettings.
            "DATABASE_URL": "postgresql+asyncpg://vechnost@db.internal:5432/vechnost",
            "ENABLE_PAYMENT": "false",
            "REDIS_URL": "redis://prod-redis:6379",
            "REDIS_DB": "1",
            "CHAT_ID": "12345",
            "SENTRY_DSN": "https://sentry.io/project",
            "MAX_CONNECTIONS": "50",
            "SESSION_TTL": "7200",
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "prod_token"
            assert settings.log_level == "DEBUG"
            assert settings.environment == "production"
            # Kept as written. RedisDsn's normal form appends /0, which would
            # have outranked REDIS_DB=1 below for a URL that names no database.
            assert settings.redis_url == "redis://prod-redis:6379"
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
        with patch.dict(
            os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "REDIS_URL": "invalid-url"}
        ):
            with pytest.raises(ValueError):
                Settings()

    def test_numeric_validation(self):
        """Test numeric field validation."""
        with patch.dict(
            os.environ, {"TELEGRAM_BOT_TOKEN": "test_token", "REDIS_DB": "invalid_number"}
        ):
            with pytest.raises(ValueError):
                Settings()


class TestConfigFunctions:
    """Test configuration utility functions."""

    @patch("vechnost_bot.config.settings")
    def test_create_bot(self, mock_settings):
        """Test bot creation."""
        mock_settings.telegram_bot_token = "test_token"

        bot = create_bot()

        assert bot.token == "test_token"

    @patch("vechnost_bot.config.settings")
    def test_get_log_level(self, mock_settings):
        """Test log level retrieval."""
        mock_settings.log_level = "DEBUG"

        level = get_log_level()

        assert level == "DEBUG"

    @patch("vechnost_bot.config.settings")
    def test_get_chat_id(self, mock_settings):
        """Test chat ID retrieval."""
        mock_settings.chat_id = "12345"

        chat_id = get_chat_id()

        assert chat_id == "12345"

    @patch("vechnost_bot.config.settings")
    def test_get_chat_id_none(self, mock_settings):
        """Test chat ID retrieval when None."""
        mock_settings.chat_id = None

        chat_id = get_chat_id()

        assert chat_id is None


class TestProductionSettings:
    """ENVIRONMENT=production refuses to start on development defaults.

    Every default in Settings suits a laptop and fails open in production:
    no ENABLE_PAYMENT is a free paywall, no DATABASE_URL a SQLite file inside
    the container. Each of these starts and serves without complaint, which
    is the problem; production must say what it means or not start at all.
    """

    # A complete production configuration. The password is made up, and
    # "example" keeps tests/test_no_secrets.py from reading it as a leak.
    GOOD = {
        "TELEGRAM_BOT_TOKEN": "123:example-token-secret",
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://vechnost:example-pw-hunter2@db.internal:5432/vechnost",
        "ENABLE_PAYMENT": "true",
        "TRIBUTE_API_KEY": "example-tribute-key",
        "WEBAPP_URL": "https://vechnost.example/app/",
    }

    def _settings(self, **overrides):
        env = {**self.GOOD, **overrides}
        env = {name: value for name, value in env.items() if value is not None}
        with patch.dict(os.environ, env, clear=True):
            return Settings(_env_file=None)

    def _refusal(self, **overrides) -> str:
        with pytest.raises(ProductionConfigError) as refused:
            self._settings(**overrides)
        return str(refused.value)

    def test_a_complete_production_configuration_starts(self):
        settings = self._settings()
        assert settings.is_production
        assert settings.enable_payment is True

    def test_payments_may_be_off_if_that_is_said_out_loud(self):
        settings = self._settings(ENABLE_PAYMENT="false", TRIBUTE_API_KEY=None)
        assert settings.enable_payment is False

    def test_development_defaults_are_refused_all_at_once(self):
        """Every missing variable in one message, not one per deploy."""
        message = self._refusal(DATABASE_URL=None, ENABLE_PAYMENT=None)
        assert "DATABASE_URL is not set" in message
        assert "ENABLE_PAYMENT is not set" in message

    def test_the_sync_driver_is_refused(self):
        """Railway's own variable is postgresql://, which the async engine cannot use."""
        message = self._refusal(DATABASE_URL="postgresql://u:p@db.internal:5432/x")
        assert "postgresql+asyncpg" in message
        assert "not postgresql" in message

    def test_sqlite_is_refused_even_when_set_explicitly(self):
        message = self._refusal(DATABASE_URL="sqlite+aiosqlite:///./vechnost.db")
        assert "DATABASE_URL must be PostgreSQL" in message

    def test_a_paywall_without_the_tribute_key_is_refused(self):
        message = self._refusal(TRIBUTE_API_KEY=None)
        assert "TRIBUTE_API_KEY" in message

    @pytest.mark.parametrize(
        "url", ["http://vechnost.example/app/", "vechnost.example/app", "https://"]
    )
    def test_a_mini_app_url_that_is_not_https_is_refused(self, url):
        assert "WEBAPP_URL must be an https:// address" in self._refusal(WEBAPP_URL=url)

    def test_no_mini_app_at_all_is_allowed(self):
        assert self._settings(WEBAPP_URL=None).webapp_url is None

    def test_the_refusal_never_repeats_a_secret(self):
        """A failed start is printed to the deploy log, so it must not echo values.

        A ValueError from a pydantic validator would: its ValidationError
        repeats the whole input, bot token and database password included.
        """
        message = self._refusal(
            ENABLE_PAYMENT=None, DATABASE_URL="postgresql://u:example-pw-hunter2@db/x"
        )
        assert "hunter2" not in message
        assert "example-token-secret" not in message
        assert "example-tribute-key" not in message

    def test_the_environment_name_is_read_loosely(self):
        with pytest.raises(ProductionConfigError):
            self._settings(ENVIRONMENT=" Production ", ENABLE_PAYMENT=None)

    def test_development_keeps_every_default(self):
        """Nothing changes for a laptop or for the test suite."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t"}, clear=True):
            settings = Settings(_env_file=None)
        assert not settings.is_production
        assert settings.database_url.startswith("sqlite")
        assert settings.enable_payment is False

    def test_the_problems_are_listed_without_raising(self):
        """`production_problems` is the list the validator reads, usable on its own."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t"}, clear=True):
            settings = Settings(_env_file=None)
        problems = production_problems(settings)
        assert any("DATABASE_URL" in p for p in problems)
        assert any("ENABLE_PAYMENT" in p for p in problems)


class TestSettingsIntegration:
    """Test settings integration with other components."""

    def test_a_prefixed_variable_is_not_read(self):
        """There is no prefix scheme, and adding one silently would be worse.

        Every field names its own variable through `validation_alias`, so
        VECHNOST_LOG_LEVEL is simply not a setting. This pins that: a
        deployment that sets the prefixed name gets the default, not a value
        it thinks it configured.
        """
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "plain_token",
            "VECHNOST_LOG_LEVEL": "WARNING",
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "plain_token"
            assert settings.log_level == "INFO"

    def test_settings_case_insensitive(self):
        """Test case insensitive environment variables."""
        env_vars = {
            "telegram_bot_token": "lowercase_token",
            "LOG_LEVEL": "ERROR",
            "environment": "staging",
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            assert settings.telegram_bot_token == "lowercase_token"
            assert settings.log_level == "ERROR"
            assert settings.environment == "staging"

    def test_settings_validation_alias(self):
        """Test validation alias for telegram token."""
        env_vars = {"TELEGRAM_BOT_TOKEN": "alias_token"}

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
            "REDIS_URL": "redis://localhost:6379",
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

        env_vars = {"TELEGRAM_BOT_TOKEN": "memory_token", "LOG_LEVEL": "INFO"}

        with patch.dict(os.environ, env_vars):
            settings = Settings()

            # Settings object should be lightweight
            size = sys.getsizeof(settings)
            assert size < 1000  # Less than 1KB


class TestSettingsErrorHandling:
    """Test settings error handling."""

    def test_invalid_redis_url(self):
        """Test invalid Redis URL handling."""
        env_vars = {"TELEGRAM_BOT_TOKEN": "test_token", "REDIS_URL": "not-a-valid-redis-url"}

        with patch.dict(os.environ, env_vars):
            with pytest.raises(ValueError):
                Settings()

    def test_invalid_numeric_values(self):
        """Test invalid numeric values."""
        test_cases = [
            ("REDIS_DB", "not_a_number"),
            ("MAX_CONNECTIONS", "invalid"),
            ("SESSION_TTL", "also_invalid"),
        ]

        for env_var, invalid_value in test_cases:
            env_vars = {"TELEGRAM_BOT_TOKEN": "test_token", env_var: invalid_value}

            with patch.dict(os.environ, env_vars):
                with pytest.raises(ValueError):
                    Settings()

    def test_missing_required_field(self):
        """Test missing required field handling."""
        with patch.dict(os.environ, {}, clear=True):
            # Pydantic reports the alias, which is the name a deployment
            # actually has to set.
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
                Settings()
