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


def setup_logging() -> None:
    """Set up logging configuration."""
    log_level = get_log_level()
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, log_level),
    )


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

    return application


def run_bot() -> None:
    """Run the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        application = create_application()
        logger.info("Starting Vechnost bot...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise
