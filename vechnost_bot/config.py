"""Configuration management for the bot using Pydantic Settings."""


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
    chat_id: str | None = Field(
        default=None,
        description="Optional chat ID for notifications"
    )

    # Sentry Configuration
    sentry_dsn: str | None = Field(
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

    # Payment Configuration
    enable_payment: bool = Field(
        default=False,
        validation_alias="ENABLE_PAYMENT",
        description="Enable payment requirement"
    )

    tribute_api_key: str | None = Field(
        default=None,
        validation_alias="TRIBUTE_API_KEY",
        description="Tribute API key for authentication"
    )

    tribute_base_url: str = Field(
        default="https://api.tribute.to",
        validation_alias="TRIBUTE_BASE_URL",
        description="Tribute API base URL"
    )

    tribute_payment_url: str = Field(
        default="https://tribute.to/vechnost",
        validation_alias="TRIBUTE_PAYMENT_URL",
        description="Tribute payment page URL for users"
    )

    webhook_secret: str | None = Field(
        default=None,
        validation_alias="WEBHOOK_SECRET",
        description="Webhook signature secret"
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./vechnost.db",
        validation_alias="DATABASE_URL",
        description="Database connection URL"
    )

    # Mini App Configuration
    webapp_url: str | None = Field(
        default=None,
        validation_alias="WEBAPP_URL",
        description="HTTPS URL of the Telegram Mini App (e.g. https://<railway-app>/app). "
                    "When set, the bot shows a 'Play in app' button."
    )

    bot_username: str | None = Field(
        default="tvoya_vechnost_bot",
        validation_alias="BOT_USERNAME",
        description="Bot username without @, used for the brand watermark on "
                    "shared card images and share links."
    )

    # Gift certificates
    gift_product_id: str | None = Field(
        default=None,
        validation_alias="GIFT_PRODUCT_ID",
        description="Tribute product id for the gift certificate. Payments for "
                    "this product produce a certificate instead of buyer access."
    )

    gift_payment_url: str | None = Field(
        default=None,
        validation_alias="GIFT_PAYMENT_URL",
        description="Tribute payment page for the gift certificate product. "
                    "The gift button is hidden when neither this nor a synced "
                    "gift product link is available."
    )

    # Daily card push
    daily_card_enabled: bool = Field(
        default=True,
        validation_alias="DAILY_CARD_ENABLED",
        description="Send the daily card push to registered users."
    )

    daily_card_hour_utc: int = Field(
        default=17,
        ge=0,
        le=23,
        validation_alias="DAILY_CARD_HOUR_UTC",
        description="UTC hour when the daily card is sent (17 = ~19:00 Prague)."
    )


# Global settings instance
settings = Settings()


def create_bot() -> Bot:
    """Create a Telegram bot instance."""
    return Bot(token=settings.telegram_bot_token)


def get_log_level() -> str:
    """Get the log level from settings."""
    return settings.log_level.upper()


def get_chat_id() -> str | None:
    """Get the chat ID from settings."""
    return settings.chat_id
