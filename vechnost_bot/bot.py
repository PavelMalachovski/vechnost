"""Main bot application setup."""

import logging
from datetime import UTC

from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .broadcast import (
    CANCEL,
    CONFIRM,
    broadcast_callback,
    broadcast_cancel_command,
    broadcast_command,
    broadcast_message,
)
from .config import create_bot, settings
from .handlers import (
    about_command,
    activate_certificate_command,
    handle_callback_query,
    help_command,
    invite_command,
    reset_command,
    start_command,
)
from .monitoring import initialize_monitoring, log_bot_event, track_performance
from .privacy import CALLBACK_PATTERN as DELETE_ME_PATTERN
from .privacy import delete_me_callback, delete_me_command
from .simple_redis_manager import (
    cleanup_simple_redis_auto_start,
    initialize_simple_redis_auto_start,
)


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
    from telegram import (
        BotCommand,
        BotCommandScopeChat,
        MenuButtonCommands,
        MenuButtonWebApp,
        WebAppInfo,
    )

    from .i18n import Language, get_text

    language = Language.RUSSIAN
    commands = [
        BotCommand("start", get_text("commands.start", language)),
        BotCommand("help", get_text("commands.help", language)),
        BotCommand("about", get_text("commands.about", language)),
        BotCommand("invite", get_text("commands.invite", language)),
        BotCommand("reset", get_text("commands.reset", language)),
        BotCommand("delete_me", get_text("commands.delete_me", language)),
    ]
    try:
        await application.bot.set_my_commands(commands)
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

    # /broadcast is published per chat, not globally: the global list is what
    # every user's "/" menu offers, and an admin command sitting in it invites
    # taps that can only ever be refused. Each admin gets their own list, and
    # a failure for one (most likely: they have never pressed /start, so there
    # is no chat to scope to) must not cost the others theirs.
    for admin_id in sorted(settings.admin_user_ids):
        try:
            await application.bot.set_my_commands(
                [*commands, BotCommand("broadcast", get_text("commands.broadcast", language))],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Could not publish /broadcast to admin {admin_id}: {e}"
            )


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

    # /delete_me: the question, and its two buttons. The callback is
    # registered ahead of the game's catch-all on a pattern, like the
    # broadcast's, so it never reaches the callback registry.
    application.add_handler(CommandHandler("delete_me", delete_me_command))
    application.add_handler(CallbackQueryHandler(
        delete_me_callback, pattern=DELETE_ME_PATTERN, block=False,
    ))

    # The admin broadcast, and only where ADMIN_IDS names somebody. With it
    # unset none of this exists: no command to type, and no button for a
    # stray callback to reach. Its callback handler is registered *before*
    # the game's catch-all, so `broadcast_*` never reaches the callback
    # registry, and with `block=False` so a send to thousands of people runs
    # as its own task instead of holding every other update behind it.
    admin_ids = sorted(settings.admin_user_ids)
    if admin_ids:
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("cancel", broadcast_cancel_command))
        application.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & filters.User(admin_ids) & ~filters.COMMAND,
            broadcast_message,
        ))
        application.add_handler(CallbackQueryHandler(
            broadcast_callback,
            pattern=f"^({CONFIRM}|{CANCEL})$",
            block=False,
        ))

    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Global error handler (silences "No error handlers are registered")
    application.add_error_handler(on_error)

    logger = logging.getLogger(__name__)
    logger.info("Application created with handlers:")
    logger.info("- Command handlers: start, help, reset, about, activate, invite, delete_me")
    logger.info("- Callback query handler: handle_callback_query")
    if admin_ids:
        logger.info(f"- Admin broadcast enabled for {len(admin_ids)} admin(s)")
    else:
        logger.info("- Admin broadcast disabled (ADMIN_IDS is unset)")

    # Scheduled jobs. DAILY_CARD_ENABLED governs only the daily card itself:
    # the retention sweep is the one thing that ever deletes rooms and
    # abandoned tests, and the «69 ступеней» nudge belongs to that game, so
    # both run whenever a JobQueue exists at all.
    if application.job_queue is None:
        logger.warning(
            "JobQueue is unavailable — the daily card, the 69 steps nudge "
            "and the retention sweep are all disabled; install "
            "python-telegram-bot[job-queue]"
        )
    else:
        from datetime import time

        # Deleting rows is not urgent and should not share a minute with
        # anything that messages a user, so it runs in the small hours.
        from .retention import retention_job

        application.job_queue.run_daily(
            retention_job,
            time=time(hour=3, minute=30, tzinfo=UTC),
            name="retention_sweep",
        )
        logger.info("- Retention sweep scheduled at 03:30 UTC")

        # An hour after the daily card's slot, so a pair who are due both
        # do not get them in the same second.
        from .steps69_notify import steps69_nudge_job

        application.job_queue.run_daily(
            steps69_nudge_job,
            time=time(
                hour=(settings.daily_card_hour_utc + 1) % 24, tzinfo=UTC
            ),
            name="steps69_nudge",
        )
        logger.info(
            f"- 69 steps nudge scheduled at "
            f"{(settings.daily_card_hour_utc + 1) % 24}:00 UTC"
        )

        if settings.daily_card_enabled:
            from .daily_card import daily_card_job

            application.job_queue.run_daily(
                daily_card_job,
                time=time(hour=settings.daily_card_hour_utc, tzinfo=UTC),
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
