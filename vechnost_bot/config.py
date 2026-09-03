"""Configuration management for the bot using Pydantic Settings."""

import logging

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Bot

logger = logging.getLogger(__name__)


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
        description="Optional second key webhooks may be signed with, for a "
                    "relay or a test harness in front of the endpoint. Tribute "
                    "itself signs with TRIBUTE_API_KEY; this is accepted "
                    "alongside it, never instead of it."
    )

    admin_ids: str | None = Field(
        default=None,
        validation_alias="ADMIN_IDS",
        description="Comma-separated Telegram user ids allowed to run the "
                    "bot's admin commands (/broadcast). Unset means nobody "
                    "is: the commands are not registered at all, which is "
                    "the safe default for a bot that can message everyone."
    )

    admin_token: str | None = Field(
        default=None,
        validation_alias="ADMIN_TOKEN",
        description="Bearer token for the /admin endpoints. Falls back to "
                    "TRIBUTE_API_KEY so existing deployments keep working, "
                    "but set it: TRIBUTE_API_KEY is an outbound credential "
                    "and reusing it as an inbound password means one leak "
                    "costs both."
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

    webapp_short_name: str | None = Field(
        default=None,
        validation_alias="WEBAPP_SHORT_NAME",
        description="The short name of a *named* Mini App, made in BotFather "
                    "with /newapp. With it, an invite is a direct link "
                    "(t.me/<bot>/<short name>?startapp=...) that opens the app "
                    "on the right screen in one tap."
    )

    webapp_main_app: bool = Field(
        default=False,
        validation_alias="WEBAPP_MAIN_APP",
        description="Set when the bot has a Main Mini App (BotFather -> Bot "
                    "Settings -> Configure Mini App). Its direct link carries "
                    "no short name at all — t.me/<bot>?startapp=... — which is "
                    "why this is its own switch rather than a value in "
                    "WEBAPP_SHORT_NAME. One tap, same as a named app; the "
                    "short name wins if somehow both are configured. With "
                    "neither, invites fall back to t.me/<bot>?start=..., where "
                    "the bot answers with a button into the app."
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

    # HTTP hardening
    cors_allow_origins: str | None = Field(
        default=None,
        validation_alias="CORS_ALLOW_ORIGINS",
        description="Comma-separated origins allowed to read API responses "
                    "from script. The Mini App is same-origin and needs none, "
                    "so the default is no allowance at all."
    )

    allowed_hosts: str | None = Field(
        default=None,
        validation_alias="ALLOWED_HOSTS",
        description="Comma-separated hostnames this deployment answers to. "
                    "Set it in production: unset, a forged Host header is "
                    "accepted."
    )

    # Referrals
    referral_payment_url: str | None = Field(
        default=None,
        validation_alias="REFERRAL_PAYMENT_URL",
        description="Tribute page for the discounted product shown to users "
                    "who arrived through someone's referral link. Unset means "
                    "referrals are still tracked but everyone pays full price."
    )

    referral_discount_percent: int = Field(
        default=10,
        ge=1,
        le=90,
        validation_alias="REFERRAL_DISCOUNT_PERCENT",
        description="What the referral page is worth, for the copy only. The "
                    "price itself lives in the Tribute product."
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

    @property
    def admin_secret(self) -> str | None:
        """The secret /admin authenticates against, or None when unset."""
        return self.admin_token or self.tribute_api_key

    @property
    def admin_user_ids(self) -> frozenset[int]:
        """The Telegram ids ADMIN_IDS names, as numbers.

        A malformed entry is dropped with a warning rather than raised: this
        is read at import, so one typo in a deployment variable would
        otherwise take the whole bot down, and dropping it fails closed —
        that id is simply not an admin until the value is fixed.
        """
        if not self.admin_ids:
            return frozenset()
        ids: set[int] = set()
        for part in self.admin_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                logger.warning(f"ADMIN_IDS: ignoring {part!r}, not a Telegram id")
        return frozenset(ids)

    def _webapp_screen_url(self, screen: str) -> str | None:
        """The Mini App URL that opens straight on one screen."""
        if not self.webapp_url:
            return None
        separator = "&" if "?" in self.webapp_url else "?"
        return f"{self.webapp_url}{separator}screen={screen}"

    def webapp_join_url(self, screen: str, code: str) -> str | None:
        """The Mini App URL that opens a screen already holding an invite code.

        What the bot's own button points at when someone taps a
        `t.me/<bot>?start=s69_XXXXXX` link: the app reads both parameters on
        boot and joins, so the partner never types a code.
        """
        base = self._webapp_screen_url(screen)
        return f"{base}&code={code}" if base else None

    @property
    def webapp_library_url(self) -> str | None:
        """The Mini App URL that opens straight on the Library screen."""
        return self._webapp_screen_url("library")

    @property
    def webapp_steps69_url(self) -> str | None:
        """The Mini App URL that opens straight on the 69 Steps board."""
        return self._webapp_screen_url("steps69")


# Global settings instance. pydantic-settings reads every field from the
# environment, which mypy cannot see, so it reports the one required field as
# a missing argument.
settings = Settings()  # type: ignore[call-arg]


def create_bot() -> Bot:
    """Create a Telegram bot instance."""
    return Bot(token=settings.telegram_bot_token)


def get_log_level() -> str:
    """Get the log level from settings."""
    return settings.log_level.upper()


def get_chat_id() -> str | None:
    """Get the chat ID from settings."""
    return settings.chat_id
