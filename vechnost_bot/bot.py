"""Main bot application setup."""

import logging
from datetime import time, timedelta

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
    free_text_hint,
    handle_callback_query,
    help_command,
    invite_command,
    reset_command,
    start_command,
)
from .jobs import DailyJob, schedule
from .monitoring import initialize_monitoring, log_bot_event, track_performance
from .privacy import CALLBACK_PATTERN as DELETE_ME_PATTERN
from .privacy import delete_me_callback, delete_me_command
from .storage import MAX_SESSIONS, RedisSessionStore, close_session_store, session_store


def setup_logging() -> None:
    """Set up logging configuration."""
    # Initialize monitoring and structured logging
    initialize_monitoring()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global PTB error handler: log the failure, and tell the person.

    Transient network noise is logged compactly and the rest in full, as
    before. What is new is the second half: a command that failed (/start,
    /help, /about...) used to leave its sender with silence, which reads as
    a dead bot. They now get one short line and never a traceback. Errors
    with no chat behind them - a failed poll, a scheduled job - have nobody
    to tell.
    """
    logger = logging.getLogger(__name__)
    error = context.error

    if isinstance(error, Conflict):
        # Another instance polled getUpdates — normal for a short window during
        # redeploys; a sustained stream of these means two services run the bot.
        logger.warning("getUpdates conflict: another bot instance is polling (deploy overlap?)")
        return
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning(f"Transient Telegram network error: {error}")
    else:
        logger.error("Unhandled error while processing update", exc_info=error)
        log_bot_event("unhandled_error", error=str(error))

    await _apologise(update, context)


async def _apologise(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One short line to the chat the failed update came from, if any."""
    from telegram import Update

    from .i18n import Language, get_text

    chat = update.effective_chat if isinstance(update, Update) else None
    if chat is None:
        return
    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=get_text("errors.something_went_wrong", Language.RUSSIAN),
        )
    except Exception as e:
        # Most likely the same outage that caused the error, or a chat that
        # blocked the bot. Nothing more to be done for this update.
        logging.getLogger(__name__).warning(f"Could not tell chat {chat.id} about the error: {e}")


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
                [
                    *commands,
                    BotCommand("broadcast", get_text("commands.broadcast", language)),
                    BotCommand("stats", get_text("commands.stats", language)),
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Could not publish /broadcast to admin {admin_id}: {e}"
            )


async def _report_session_store() -> None:
    """Say where sessions live, and whether a configured Redis answers.

    A Redis that does not answer is logged rather than fatal: the bot
    shares its deployment with the web process, and a crash here would take
    payments and the Mini App down with it, in a restart loop, for want of
    a store whose loss costs a player their place in a deck.
    """
    logger = logging.getLogger(__name__)
    store = session_store()
    if isinstance(store, RedisSessionStore):
        try:
            await store.ping()
            logger.info("Sessions: in the Redis REDIS_URL names")
        except Exception as e:
            logger.error(
                f"Sessions: the Redis REDIS_URL names does not answer ({e}); "
                "taps that need a session fail until it does"
            )
    else:
        logger.info(
            f"Sessions: in memory, kept {settings.session_ttl}s after the "
            f"last save, at most {MAX_SESSIONS}"
        )


async def _post_init(application: Application) -> None:
    await _report_session_store()
    await _publish_entry_points(application)


async def _post_shutdown(application: Application) -> None:
    await close_session_store()


def create_application() -> Application:
    """Create and configure the Telegram application."""
    bot = create_bot()
    application = (
        Application.builder()
        .bot(bot)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

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
        from .stats import stats_command

        # The funnel, read off the events table: same gate as the broadcast.
        application.add_handler(CommandHandler("stats", stats_command))
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

    # Text nobody asked for - a greeting, a certificate code pasted without
    # /activate - gets a hint rather than silence. Private chats only, new
    # messages only (not edits), and registered after the admin's broadcast
    # capture, which takes an admin's messages first in the same group.
    application.add_handler(MessageHandler(
        filters.UpdateType.MESSAGE
        & filters.ChatType.PRIVATE
        & filters.TEXT
        & ~filters.COMMAND,
        free_text_hint,
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

    # Scheduled jobs. The heartbeat is its own every-minute job; the three
    # daily ones run through `jobs.py`, which claims each day's run in the
    # database so a restart resumes it and a second bot cannot repeat it.
    if application.job_queue is not None:
        from .heartbeat import register_heartbeat

        register_heartbeat(application)  # the pulse /health/deep reads
    schedule(application, daily_jobs())

    return application


def daily_jobs() -> list[DailyJob]:
    """What runs once a day, and when (UTC).

    DAILY_CARD_ENABLED governs only the daily card itself: the retention
    sweep is the one thing that ever deletes rooms and abandoned tests, and
    the «69 ступеней» nudge belongs to that game, so both run regardless.
    Each window is how late a missed or interrupted run may still go out.
    """
    from .daily_card import JOB_NAME as DAILY_CARD
    from .daily_card import run_daily_card
    from .retention import JOB_NAME as RETENTION
    from .retention import run_retention
    from .steps69_notify import JOB_NAME as NUDGE
    from .steps69_notify import run_steps69_nudge

    hour = settings.daily_card_hour_utc
    jobs = [
        # Deleting rows is not urgent and should not share a minute with
        # anything that messages a user, so it runs in the small hours.
        DailyJob(RETENTION, time(3, 30), timedelta(hours=12), run_retention),
        # An hour after the daily card's slot, so a pair who are due both
        # do not get them in the same second.
        DailyJob(NUDGE, time((hour + 1) % 24), timedelta(hours=3), run_steps69_nudge),
    ]
    if settings.daily_card_enabled:
        jobs.append(DailyJob(DAILY_CARD, time(hour), timedelta(hours=3), run_daily_card))
    return jobs


@track_performance("bot_startup")
def run_bot() -> None:
    """Run the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        application = create_application()
        logger.info("Starting Vechnost bot...")
        log_bot_event("bot_started", session_store=session_store().kind)
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        log_bot_event("bot_error", error=str(e))
        raise
