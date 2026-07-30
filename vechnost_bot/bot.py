"""Main bot application setup."""

import logging
import asyncio

from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .config import create_bot, get_log_level
from .handlers import (
    handle_callback_query,
    help_command,
    reset_command,
    start_command,
    about_command,
    activate_certificate_command,
)
from .monitoring import initialize_monitoring, log_bot_event, track_performance
from .simple_redis_manager import initialize_simple_redis_auto_start, cleanup_simple_redis_auto_start


def setup_logging() -> None:
    """Set up logging configuration."""
    # Initialize monitoring and structured logging
    initialize_monitoring()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global PTB error handler: keep transient noise compact, log the rest fully."""
    logger = logging.getLogger(__name__)
    error = context.error

    if isinstance(error, Conflict):
        # Another instance polled getUpdates — normal for a short window during
        # redeploys; a sustained stream of these means two services run the bot.
        logger.warning("getUpdates conflict: another bot instance is polling (deploy overlap?)")
        return
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning(f"Transient Telegram network error: {error}")
        return

    logger.error("Unhandled error while processing update", exc_info=error)
    log_bot_event("unhandled_error", error=str(error))


def create_application() -> Application:
    """Create and configure the Telegram application."""
    bot = create_bot()
    application = Application.builder().bot(bot).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("activate", activate_certificate_command))

    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Global error handler (silences "No error handlers are registered")
    application.add_error_handler(on_error)

    logger = logging.getLogger(__name__)
    logger.info("Application created with handlers:")
    logger.info("- Command handlers: start, help, reset, about, activate")
    logger.info("- Callback query handler: handle_callback_query")

    # Daily card push
    from .config import settings
    if settings.daily_card_enabled:
        if application.job_queue is None:
            logger.warning(
                "Daily card enabled but JobQueue is unavailable — "
                "install python-telegram-bot[job-queue]"
            )
        else:
            from datetime import time, timezone

            from .daily_card import daily_card_job

            application.job_queue.run_daily(
                daily_card_job,
                time=time(hour=settings.daily_card_hour_utc, tzinfo=timezone.utc),
                name="daily_card",
            )
            logger.info(f"- Daily card scheduled at {settings.daily_card_hour_utc}:00 UTC")

    return application


def initialize_redis_sync() -> bool:
    """Initialize Redis with auto-start (synchronous)."""
    logger = logging.getLogger(__name__)
    try:
        redis_started = initialize_simple_redis_auto_start()
        if redis_started:
            logger.info("Redis auto-started successfully")
        else:
            logger.warning("Redis auto-start failed, using in-memory storage")
        return redis_started
    except Exception as e:
        logger.error(f"Redis initialization error: {e}")
        return False


def cleanup_redis_sync():
    """Cleanup Redis (synchronous)."""
    try:
        cleanup_simple_redis_auto_start()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Redis cleanup error: {e}")


@track_performance("bot_startup")
def run_bot() -> None:
    """Run the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # Initialize Redis with auto-start (synchronous)
        redis_started = initialize_redis_sync()

        application = create_application()
        logger.info("Starting Vechnost bot...")
        log_bot_event("bot_started", redis_enabled=redis_started)
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
        cleanup_redis_sync()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        log_bot_event("bot_error", error=str(e))
        cleanup_redis_sync()
        raise
