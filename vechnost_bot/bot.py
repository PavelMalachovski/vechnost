"""Main bot application setup."""

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .config import create_bot, get_log_level
from .handlers import (
    handle_callback_query,
    help_command,
    reset_command,
    start_command,
)
from .monitoring import initialize_monitoring, log_bot_event, track_performance


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


@track_performance("bot_startup")
def run_bot() -> None:
    """Run the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        application = create_application()
        logger.info("Starting Vechnost bot...")
        log_bot_event("bot_started")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        log_bot_event("bot_error", error=str(e))
        raise
