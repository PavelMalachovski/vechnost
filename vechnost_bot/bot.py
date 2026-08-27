"""Main bot application setup."""

import logging
import asyncio

from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .config import create_bot, get_log_level
from .handlers import (
    handle_callback_query,
    help_command,
    invite_command,
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


async def _publish_entry_points(application: Application) -> None:
    """Give a user with an empty chat a way back in.

    Clearing the history deletes every button the bot ever sent, and with the
    game living in the Mini App there is nothing left on screen to tap: the
    user has to know to type /start. Two things survive a cleared history and
    are set here, once, at startup.

    The menu button is the blue control beside the message box; pointed at
    the Mini App it opens the app directly. The command list is what the "/"
    menu offers, which is where /start becomes discoverable again.

    Neither is worth taking the bot down for, so a failure is logged and the
    bot starts anyway.
    """
    from telegram import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

    from .config import settings
    from .i18n import Language, get_text

    language = Language.RUSSIAN
    try:
        await application.bot.set_my_commands([
            BotCommand("start", get_text("commands.start", language)),
            BotCommand("help", get_text("commands.help", language)),
            BotCommand("about", get_text("commands.about", language)),
            BotCommand("invite", get_text("commands.invite", language)),
            BotCommand("reset", get_text("commands.reset", language)),
        ])
        if settings.webapp_url:
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=get_text("commands.menu_button", language),
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            )
        else:
            # No app to open: the "/" menu is the only way back, so make the
            # button open that rather than leave it on Telegram's default.
            await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not publish entry points: {e}")


def create_application() -> Application:
    """Create and configure the Telegram application."""
    bot = create_bot()
    application = Application.builder().bot(bot).post_init(_publish_entry_points).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("activate", activate_certificate_command))
    application.add_handler(CommandHandler("invite", invite_command))

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

            # An hour after the daily card, so a pair who are due both do not
            # get them in the same second.
            from .steps69_notify import steps69_nudge_job

            application.job_queue.run_daily(
                steps69_nudge_job,
                time=time(
                    hour=(settings.daily_card_hour_utc + 1) % 24, tzinfo=timezone.utc
                ),
                name="steps69_nudge",
            )
            logger.info(
                f"- 69 steps nudge scheduled at "
                f"{(settings.daily_card_hour_utc + 1) % 24}:00 UTC"
            )

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
