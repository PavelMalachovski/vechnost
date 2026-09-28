"""Nudge a pair whose piece is still standing on the board.

«69 ступеней» has no TTL: a game left on cell 45 on a Tuesday is still on
cell 45 on Friday. That is the right behaviour and also the reason this
module exists, because a game nobody is reminded of is a game nobody
finishes.

Sent once per game, ever. `Steps69Game.resume_notified_at` is the record,
and rolling again clears it, so a pair who come back, play on and stall a
second time can be nudged about that stall too.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from .config import settings
from .i18n import Language, get_text
from .jobs import Run

logger = logging.getLogger(__name__)

# Its row in `job_runs` and its Sentry monitor.
JOB_NAME = "steps69_nudge"

# Long enough that a pair mid-game are never interrupted, short enough that
# the game is still something they remember starting.
IDLE_BEFORE_NUDGE = timedelta(hours=20)

# Past this the game was abandoned rather than paused, and a message about
# it reads as the app going through their history rather than helping.
GIVE_UP_AFTER = timedelta(days=7)


def _keyboard(language: Language) -> InlineKeyboardMarkup | None:
    """The "continue" button, or None when WEBAPP_URL is unset.

    `web_app=`, not `url=`: a plain url opens Telegram's in-app browser,
    where `Telegram.WebApp.initData` is empty, so every /api/steps69 call
    would 401 in production.
    """
    if not settings.webapp_steps69_url:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("steps69.resume_button", language),
                    web_app=WebAppInfo(url=settings.webapp_steps69_url),
                )
            ]
        ]
    )


async def nudge_stalled_games(bot: Bot, run: Run | None = None) -> int:
    """Message both partners of every stalled game. Returns games nudged.

    `run` is the day's claimed run (`jobs.py`): games are taken in id order
    after its cursor and each is flagged the moment somebody is reached, so
    a run cut short by a restart is resumed without messaging the pairs it
    already reached. Without one - a test, a hand-run - nothing is recorded
    but the flags.
    """
    from . import broadcast
    from .payments.database import get_db
    from .payments.repositories import Steps69Repository, UserRepository

    now = datetime.utcnow()
    run = run or Run.detached_for(JOB_NAME, now.date())
    async with get_db() as session:
        games = await Steps69Repository.stalled(
            session,
            idle_since=now - IDLE_BEFORE_NUDGE,
            give_up_before=now - GIVE_UP_AFTER,
            after_id=run.cursor,
        )
        # Read what the messages need before leaving the session: the sends
        # happen outside it, so a lazy load afterwards would have no session
        # to load from.
        #
        # Each partner hears about their own piece. They walk the board
        # separately now, so one shared cell number would be wrong for at
        # least one of them, and telling someone their piece waits on a cell
        # it has never stood on is worse than saying nothing.
        pending = [
            (
                game.id,
                [
                    (user_id, position)
                    for user_id, position in (
                        (game.creator_telegram_user_id, game.creator_position),
                        (game.guest_telegram_user_id, game.guest_position),
                    )
                    if user_id
                ],
            )
            for game in games
        ]

    if not pending:
        return 0

    languages: dict[int, Language] = {}
    try:
        async with get_db() as session:
            for _, recipients in pending:
                for user_id, _ in recipients:
                    user = await UserRepository.get_by_telegram_id(session, user_id)
                    languages[user_id] = Language.coerce(user.language if user else None)
    except Exception as e:
        # A language lookup must never cost a pair their nudge.
        logger.warning(f"Steps69 nudge: language lookup failed: {e}")

    nudged = 0
    for game_id, recipients in pending:
        run.check()
        reached = False
        for user_id, position in recipients:
            language = languages.get(user_id, Language.RUSSIAN)

            async def send(
                chat_id: int, _language: Language = language, _cell: int = position
            ) -> Any:
                return await bot.send_message(
                    chat_id=chat_id,
                    text=get_text("steps69.resume", _language, cell=_cell),
                    reply_markup=_keyboard(_language),
                )

            # The delivery loop every bulk send shares: Telegram's own
            # `retry_after` is waited out, and a partner who has blocked the
            # bot - or never opened a chat with it, having joined through
            # the Mini App - is opted out of the daily push as well.
            status = await broadcast.deliver(send, user_id)
            if status == broadcast.SENT:
                reached = True
            elif status == broadcast.BLOCKED:
                logger.info(f"Steps69 nudge: user {user_id} has no chat with the bot or blocked it")
            await asyncio.sleep(broadcast.SECONDS_BETWEEN_SENDS)

        # Flagged only once somebody was actually reached. Flagging before
        # the sends meant a pair the bot could not message that day (say, a
        # guest who joined through the Mini App and never opened a chat
        # with the bot) was written off forever; now the job simply tries
        # again tomorrow, until the give-up window closes over the game.
        # And flagged at once, game by game: a run cut short and resumed
        # must not message the pairs it had already reached.
        if reached:
            async with get_db() as session:
                await Steps69Repository.mark_resume_notified(session, [game_id], now)
            nudged += 1
        await run.advance(game_id, broadcast.SENT if reached else broadcast.FAILED)

    logger.info(f"Steps69 nudge: reminded {nudged}/{len(pending)} stalled games")
    return nudged


async def run_steps69_nudge(bot: Bot, run: Run) -> None:
    """The scheduler's entry point (`jobs.DailyJob.run`)."""
    await nudge_stalled_games(bot, run)
