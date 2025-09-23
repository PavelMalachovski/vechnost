"""Main bot application setup."""

import logging
import asyncio

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .config import create_bot, get_log_level
from .handlers import (
    handle_callback_query,
    help_command,
    reset_command,
    start_command,
)
from .monitoring import initialize_monitoring, log_bot_event, track_performance
from .redis_manager import initialize_redis_auto_start, cleanup_redis_auto_start


def setup_logging() -> None:
    """Set up logging configuration."""
    # Initialize monitoring and structured logging
    initialize_monitoring()


def create_application() -> Application:
    """Create and configure the Telegram application."""
    bot = create_bot()
    application = Application.builder().bot(bot).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))

    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    logger = logging.getLogger(__name__)
    logger.info("Application created with handlers:")
    logger.info("- Command handlers: start, help, reset")
    logger.info("- Callback query handler: handle_callback_query")

    return application


async def initialize_redis() -> bool:
    """Initialize Redis with auto-start."""
    logger = logging.getLogger(__name__)
    try:
        redis_started = await initialize_redis_auto_start()
        if redis_started:
            logger.info("Redis auto-started successfully")
        else:
            logger.warning("Redis auto-start failed, using in-memory storage")
        return redis_started
    except Exception as e:
        logger.error(f"Redis initialization error: {e}")
        return False


@track_performance("bot_startup")
def run_bot() -> None:
    """Run the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # Initialize Redis with auto-start
        redis_started = asyncio.run(initialize_redis())

        application = create_application()
        logger.info("Starting Vechnost bot...")
        log_bot_event("bot_started", redis_enabled=redis_started)
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
        asyncio.run(cleanup_redis_auto_start())
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        log_bot_event("bot_error", error=str(e))
        asyncio.run(cleanup_redis_auto_start())
        raise
