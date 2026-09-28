"""Configuration management for the bot using Pydantic Settings."""

import logging
from urllib.parse import urlsplit

from pydantic import Field, RedisDsn, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Bot

logger = logging.getLogger(__name__)

# The one database driver the app can run on in production: the engine is
# async, and PostgreSQL is what production runs (SQLite in a container is a
# file lost on every deploy, and shared by two processes).
PRODUCTION_DATABASE_SCHEME = "postgresql+asyncpg"


class ProductionConfigError(RuntimeError):
    """A production deployment started on development defaults.

    Deliberately not a ValueError: pydantic turns a ValueError raised in a
    validator into a ValidationError whose message repeats the input, and
    the input is every setting - the bot token and the database password
    among them - which would land in the deploy log of a failed start.
    """


def production_problems(settings: "Settings") -> list[str]:
    """What stops these settings from being a production configuration.

    Every default here is a development one, and each is wrong in its own
    quiet way: no ENABLE_PAYMENT means the paywall is open, no DATABASE_URL
    means a SQLite file inside the container, a paywall without the Tribute
    key refuses every payment, and Telegram opens a Mini App over HTTPS
    only. The messages name the variable and never echo a value, since a
    value may be a secret.
    """
    problems: list[str] = []
    explicit = settings.model_fields_set

    scheme = urlsplit(settings.database_url).scheme
    if "database_url" not in explicit:
        problems.append(
            "DATABASE_URL is not set, so the database would be a SQLite file "
            "inside the container, lost on every deploy; set it to "
            f"{PRODUCTION_DATABASE_SCHEME}://..."
        )
    elif scheme != PRODUCTION_DATABASE_SCHEME:
        problems.append(
            f"DATABASE_URL must be PostgreSQL with the async driver "
            f"({PRODUCTION_DATABASE_SCHEME}://...), not {scheme or 'a URL without a scheme'}; "
            "Railway's own variable is spelled postgresql://, add +asyncpg"
        )

    if "enable_payment" not in explicit:
        problems.append(
            "ENABLE_PAYMENT is not set: say true or false, because unset "
            "means every paid card is free"
        )
    elif settings.enable_payment and not settings.tribute_api_key:
        problems.append(
            "TRIBUTE_API_KEY is not set, and with ENABLE_PAYMENT=true every "
            "Tribute webhook would be refused unverified"
        )

    if settings.webapp_url:
        url = urlsplit(settings.webapp_url)
        if url.scheme != "https" or not url.netloc:
            problems.append(
                "WEBAPP_URL must be an https:// address: Telegram opens a "
                "Mini App over HTTPS only, and refuses the whole /start "
                "greeting that carries a button to anything else"
            )
    return problems


class Settings(BaseSettings):
    """Application settings using Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # Telegram Bot Configuration
    telegram_bot_token: str = Field(
        validation_alias="TELEGRAM_BOT_TOKEN", description="Telegram bot token"
    )

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")

    # Environment Configuration
    environment: str = Field(
        default="development",
        description="Application environment. `production` makes the "
        "service refuse to start on development defaults "
        "(see production_problems), and tags Sentry events.",
    )

    # Sessions. Unset (the default) keeps them in the bot process's memory,
    # bounded by SESSION_TTL and a size cap; set, they live in that Redis.
    # This had a default of redis://localhost:6379 that nothing read: the
    # bot started a Redis of its own on localhost whatever the URL said.
    # Checked as a Redis DSN but kept as written (see the validator below).
    redis_url: str | None = Field(
        default=None,
        description="Redis for bot sessions. Unset: sessions stay in the bot process's memory.",
    )

    redis_db: int = Field(default=0, description="Redis database number, when REDIS_URL names none")

    # Sentry Configuration
    sentry_dsn: str | None = Field(default=None, description="Sentry DSN for error tracking")

    # Performance Configuration
    max_connections: int = Field(default=20, description="Maximum Redis connections")

    session_ttl: int = Field(
        default=3600,
        description="Seconds a bot session outlives its last save, in memory and in Redis alike",
    )

    @field_validator("redis_url", mode="before")
    @classmethod
    def _redis_url_as_written(cls, value: object) -> object:
        """A Redis DSN, kept exactly as written; blank means unset.

        `REDIS_URL=` in a deployment means no Redis, not a broken one. And
        the URL is not stored in pydantic's normalised form, which appends
        `/0` to a URL that names no database: that would silently outrank
        REDIS_DB, whose whole job is to choose the database such a URL
        leaves open.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        TypeAdapter(RedisDsn).validate_python(value)
        return str(value).strip()

    # Payment Configuration
    enable_payment: bool = Field(
        default=False, validation_alias="ENABLE_PAYMENT", description="Enable payment requirement"
    )

    tribute_api_key: str | None = Field(
        default=None,
        validation_alias="TRIBUTE_API_KEY",
        description="Tribute API key for authentication",
    )

    tribute_base_url: str = Field(
        default="https://api.tribute.to",
        validation_alias="TRIBUTE_BASE_URL",
        description="Tribute API base URL",
    )

    tribute_payment_url: str = Field(
        default="https://tribute.to/vechnost",
        validation_alias="TRIBUTE_PAYMENT_URL",
        description="Tribute payment page URL for users",
    )

    webhook_secret: str | None = Field(
        default=None,
        validation_alias="WEBHOOK_SECRET",
        description="Optional second key webhooks may be signed with, for a "
        "relay or a test harness in front of the endpoint. Tribute "
        "itself signs with TRIBUTE_API_KEY; this is accepted "
        "alongside it, never instead of it.",
    )

    admin_ids: str | None = Field(
        default=None,
        validation_alias="ADMIN_IDS",
        description="Comma-separated Telegram user ids allowed to run the "
        "bot's admin commands (/broadcast). Unset means nobody "
        "is: the commands are not registered at all, which is "
        "the safe default for a bot that can message everyone.",
    )

    admin_token: str | None = Field(
        default=None,
        validation_alias="ADMIN_TOKEN",
        description="Bearer token for the /admin endpoints. Falls back to "
        "TRIBUTE_API_KEY so existing deployments keep working, "
        "but set it: TRIBUTE_API_KEY is an outbound credential "
        "and reusing it as an inbound password means one leak "
        "costs both.",
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./vechnost.db",
        validation_alias="DATABASE_URL",
        description="Database connection URL",
    )

    # Mini App Configuration
    webapp_url: str | None = Field(
        default=None,
        validation_alias="WEBAPP_URL",
        description="HTTPS URL of the Telegram Mini App (e.g. https://<railway-app>/app). "
        "When set, the bot shows a 'Play in app' button.",
    )

    bot_username: str | None = Field(
        default="tvoya_vechnost_bot",
        validation_alias="BOT_USERNAME",
        description="Bot username without @, used for the brand watermark on "
        "shared card images and share links.",
    )

    webapp_short_name: str | None = Field(
        default=None,
        validation_alias="WEBAPP_SHORT_NAME",
        description="The short name of a *named* Mini App, made in BotFather "
        "with /newapp. With it, an invite is a direct link "
        "(t.me/<bot>/<short name>?startapp=...) that opens the app "
        "on the right screen in one tap.",
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
        "the bot answers with a button into the app.",
    )

    # The product the paywall sells
    access_product_id: str | None = Field(
        default=None,
        validation_alias="ACCESS_PRODUCT_ID",
        description="Tribute product id of the access itself. The Mini App's "
        "buy button, the price it shows and the bot's purchase "
        "button use exactly this product. Unset, they use the "
        "cheapest synced product that is neither the gift "
        "(GIFT_PRODUCT_ID) nor the referral discount "
        "(REFERRAL_PAYMENT_URL).",
    )

    # Gift certificates
    gift_product_id: str | None = Field(
        default=None,
        validation_alias="GIFT_PRODUCT_ID",
        description="Tribute product id for the gift certificate. Payments for "
        "this product produce a certificate instead of buyer access.",
    )

    gift_payment_url: str | None = Field(
        default=None,
        validation_alias="GIFT_PAYMENT_URL",
        description="Tribute payment page for the gift certificate product. "
        "The gift button is hidden when neither this nor a synced "
        "gift product link is available.",
    )

    # HTTP hardening
    cors_allow_origins: str | None = Field(
        default=None,
        validation_alias="CORS_ALLOW_ORIGINS",
        description="Comma-separated origins allowed to read API responses "
        "from script. The Mini App is same-origin and needs none, "
        "so the default is no allowance at all.",
    )

    trusted_proxy_hops: int = Field(
        default=1,
        ge=1,
        le=5,
        validation_alias="TRUSTED_PROXY_HOPS",
        description="How many proxies stand between the internet and this "
        "app and append to X-Forwarded-For. The rate limiter "
        "reads the client address that many entries from the "
        "end of the header; the entries before it were written "
        "by the client. One on Railway; two with a CDN in front.",
    )

    allowed_hosts: str | None = Field(
        default=None,
        validation_alias="ALLOWED_HOSTS",
        description="Comma-separated hostnames this deployment answers to. "
        "Set it in production: unset, a forged Host header is "
        "accepted.",
    )

    # Referrals
    referral_payment_url: str | None = Field(
        default=None,
        validation_alias="REFERRAL_PAYMENT_URL",
        description="Tribute page for the discounted product shown to users "
        "who arrived through someone's referral link. Unset means "
        "referrals are still tracked but everyone pays full price.",
    )

    referral_discount_percent: int = Field(
        default=10,
        ge=1,
        le=90,
        validation_alias="REFERRAL_DISCOUNT_PERCENT",
        description="What the referral page is worth, for the copy only. The "
        "price itself lives in the Tribute product.",
    )

    # Daily card push
    daily_card_enabled: bool = Field(
        default=True,
        validation_alias="DAILY_CARD_ENABLED",
        description="Send the daily card push to registered users.",
    )

    daily_card_hour_utc: int = Field(
        default=17,
        ge=0,
        le=23,
        validation_alias="DAILY_CARD_HOUR_UTC",
        description="UTC hour when the daily card is sent (17 = ~19:00 Prague).",
    )

    @property
    def is_production(self) -> bool:
        """Whether this is the production deployment (ENVIRONMENT=production)."""
        return self.environment.strip().lower() == "production"

    @model_validator(mode="after")
    def _refuse_development_defaults_in_production(self) -> "Settings":
        """Stop a production start on settings that only suit development.

        Each of these used to fail open, and quietly: the service came up
        and served, free, from a file in the container. Refusing to start
        means the deploy's healthcheck never passes and the previous
        deploy keeps serving, with a log line naming every variable to fix.
        """
        if self.is_production:
            problems = production_problems(self)
            if problems:
                raise ProductionConfigError(
                    "ENVIRONMENT=production, but the configuration is not "
                    "one to start with:\n- " + "\n- ".join(problems)
                )
        return self

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
    def webapp_steps69_url(self) -> str | None:
        """The Mini App URL that opens straight on the 69 Steps board."""
        return self._webapp_screen_url("steps69")


# Global settings instance. pydantic-settings reads every field from the
# environment, which mypy cannot see, so it reports the one required field as
# a missing argument.
settings = Settings()  # type: ignore[call-arg]


# Connections to the Bot API. python-telegram-bot's default is one, with a
# one-second wait for it: with updates handled side by side and a job
# sending at the same time, a tap queued behind the daily push failed with
# `Pool timeout` after a second, and the user saw nothing. The getUpdates
# long poll has its own connection and is not counted here.
BOT_API_CONNECTIONS = 64
BOT_API_POOL_TIMEOUT = 10.0


def create_bot() -> Bot:
    """The bot the application runs on, with a pool sized for concurrency."""
    from telegram.request import HTTPXRequest

    return Bot(
        token=settings.telegram_bot_token,
        request=HTTPXRequest(
            connection_pool_size=BOT_API_CONNECTIONS,
            pool_timeout=BOT_API_POOL_TIMEOUT,
        ),
    )
