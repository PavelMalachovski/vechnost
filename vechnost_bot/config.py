"""Configuration management for the bot using Pydantic Settings."""

from typing import Optional
from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Bot


class Settings(BaseSettings):
    """Application settings using Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # Telegram Bot Configuration
    telegram_bot_token: str = Field(
        validation_alias="TELEGRAM_BOT_TOKEN",
        description="Telegram bot token"
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    # Environment Configuration
    environment: str = Field(
        default="development",
        description="Application environment"
    )

    # Redis Configuration
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )

    redis_db: int = Field(
        default=0,
        description="Redis database number"
    )

    # Optional Configuration
    chat_id: Optional[str] = Field(
        default=None,
        description="Optional chat ID for notifications"
    )

    # Sentry Configuration
    sentry_dsn: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error tracking"
    )

    # Performance Configuration
    max_connections: int = Field(
        default=20,
        description="Maximum Redis connections"
    )

    session_ttl: int = Field(
        default=3600,
        description="Session TTL in seconds"
    )


# Global settings instance
settings = Settings()


def create_bot() -> Bot:
    """Create a Telegram bot instance."""
    return Bot(token=settings.telegram_bot_token)


def get_log_level() -> str:
    """Get the log level from settings."""
    return settings.log_level.upper()


def get_chat_id() -> Optional[str]:
    """Get the chat ID from settings."""
    return settings.chat_id
