"""Nudge a pair whose piece is still standing on the board.

«69 ступеней» has no TTL: a game left on cell 45 on a Tuesday is still on
cell 45 on Friday. That is the right behaviour and also the reason this
module exists, because a game nobody is reminded of is a game nobody
finishes.

Sent once per game, ever. `Steps69Game.resume_notified_at` is the record,
and rolling again clears it, so a pair who come back, play on and stall a
second time can be nudged about that stall too.
"""

import logging
from datetime import datetime, timedelta

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from .config import settings
from .i18n import Language, get_text

logger = logging.getLogger(__name__)

# Long enough that a pair mid-game are never interrupted, short enough that
# the game is still something they remember starting.
IDLE_BEFORE_NUDGE = timedelta(hours=20)

# Past this the game was abandoned rather than paused, and a message about
# it reads as the app going through their history rather than helping.
GIVE_UP_AFTER = timedelta(days=7)


def _bot() -> Bot | None:
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def _keyboard(language: Language) -> InlineKeyboardMarkup | None:
    """The "continue" button, or None when WEBAPP_URL is unset.

    `web_app=`, not `url=`: a plain url opens Telegram's in-app browser,
    where `Telegram.WebApp.initData` is empty, so every /api/steps69 call
    would 401 in production.
    """
    if not settings.webapp_steps69_url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text("steps69.resume_button", language),
            web_app=WebAppInfo(url=settings.webapp_steps69_url),
        )
    ]])


async def nudge_stalled_games(bot: Bot) -> int:
    """Message both partners of every stalled game. Returns games nudged."""
    from .payments.database import get_db
    from .payments.repositories import Steps69Repository, UserRepository

    now = datetime.utcnow()
    async with get_db() as session:
        games = await Steps69Repository.stalled(
            session,
            idle_since=now - IDLE_BEFORE_NUDGE,
            give_up_before=now - GIVE_UP_AFTER,
        )
        # Read what the messages need before leaving the session: the sends
        # happen outside it, so a lazy load afterwards would have no session
        # to load from.
        pending = [
            (
                game.position,
                [
                    user_id for user_id in (
                        game.creator_telegram_user_id,
                        game.guest_telegram_user_id,
                    ) if user_id
                ],
            )
            for game in games
        ]
        for game in games:
            game.resume_notified_at = now

    if not pending:
        return 0

    languages: dict[int, Language] = {}
    try:
        async with get_db() as session:
            for _, recipients in pending:
                for user_id in recipients:
                    user = await UserRepository.get_by_telegram_id(session, user_id)
                    languages[user_id] = Language.coerce(user.language if user else None)
    except Exception as e:
        # A language lookup must never cost a pair their nudge.
        logger.warning(f"Steps69 nudge: language lookup failed: {e}")

    nudged = 0
    for position, recipients in pending:
        reached = False
        for user_id in recipients:
            language = languages.get(user_id, Language.RUSSIAN)
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=get_text("steps69.resume", language, cell=position),
                    reply_markup=_keyboard(language),
                )
                reached = True
            except Forbidden:
                logger.info(f"Steps69 nudge: user {user_id} blocked the bot")
            except Exception as e:
                logger.warning(f"Steps69 nudge failed for {user_id}: {e}")
        if reached:
            nudged += 1

    logger.info(f"Steps69 nudge: reminded {nudged}/{len(pending)} stalled games")
    return nudged


async def steps69_nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB JobQueue entry point."""
    await nudge_stalled_games(context.bot)
