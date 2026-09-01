"""The admin broadcast: one message, delivered to every registered user.

Two front doors onto one delivery loop. `scripts/broadcast.py` is the
deliberate door — a machine someone controls, and nothing leaves without
`--confirm`. `/broadcast` in the bot is the convenient one, for when the
person who writes the announcement is not the person with a shell.

Everything that makes a bulk send survivable lives here rather than at
either door, so the two cannot drift apart: the pause between sends, the
retry that honours Telegram's own `retry_after`, and the rule that a user
who has blocked the bot is opted out of the daily push as well, because
that is the same signal.

The bot door is gated on `ADMIN_IDS`. Unset, none of it is registered:
the command does not exist, and the buttons behind it have nothing to
reach. That is deliberate — a broadcast is irreversible and reaches
everyone, so it should never be one stray callback away.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    WebAppInfo,
)
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter
from telegram.ext import ContextTypes

from .config import settings
from .i18n import Language, get_text

logger = logging.getLogger(__name__)

# Telegram's documented ceiling for bulk sends is about 30 messages a
# second, and every method counts against it, not only the sends. One
# request per recipient here, so this is roughly a third of the budget: a
# broadcast is not in a hurry, and a 429 costs more than the pause that
# would have avoided it.
SECONDS_BETWEEN_SENDS = 0.06
SEND_ATTEMPTS = 4
PROGRESS_EVERY = 25

SENT = "sent"
BLOCKED = "blocked"
FAILED = "failed"

CONFIRM = "broadcast_confirm"
CANCEL = "broadcast_cancel"

# `context.user_data` keys. Both live in the bot process and do not survive
# a restart, which `broadcast_callback` handles rather than ignores.
_AWAITING = "broadcast_awaiting"
_PREVIEW = "broadcast_preview"


@dataclass
class BroadcastReport:
    """What happened, in the shape the report to the admin is written from."""

    total: int = 0
    sent: int = 0
    blocked: int = 0
    failed: list[int] = field(default_factory=list)


def is_admin(user_id: int | None) -> bool:
    """Whether this Telegram user may run the bot's admin commands."""
    return user_id is not None and user_id in settings.admin_user_ids


def app_keyboard() -> InlineKeyboardMarkup | None:
    """The app button, so the message is also the way into what it announces.

    None when there is no app configured to open: a dead row under an
    announcement is worse than no row.
    """
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        get_text('broadcast.open_app_button', Language.RUSSIAN),
        web_app=WebAppInfo(url=settings.webapp_url),
    )]])


async def recipients() -> list[tuple[int, str | None]]:
    """Everyone the bot knows, as (telegram_user_id, first_name).

    `get_all` deliberately ignores `daily_card_opt_out`: that flag is a
    choice about the daily prompt, not consent withdrawn from the bot.
    """
    from .payments.database import get_db
    from .payments.repositories import UserRepository

    async with get_db() as session:
        users = await UserRepository.get_all(session)
        return [(u.telegram_user_id, u.first_name) for u in users]


async def _opt_out(user_id: int) -> None:
    """Stop pushing to a user who is gone. Never raises: it is a side effect
    of a delivery result, and losing it must not lose the delivery result."""
    from .payments.database import get_db
    from .payments.repositories import UserRepository

    try:
        async with get_db() as session:
            await UserRepository.set_daily_card_opt_out(session, user_id, True)
    except Exception as e:
        logger.warning(f"Broadcast: could not opt {user_id} out of the daily push: {e}")


async def deliver(send: Callable[[int], Awaitable[Any]], user_id: int) -> str:
    """One recipient, with the retries that make a bulk send survivable.

    Returns SENT, BLOCKED (the user blocked the bot or the account is gone —
    retrying is pointless, and they are opted out of the daily push too) or
    FAILED (attempts exhausted, or Telegram refused for a reason of its own).
    """
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            await send(user_id)
            return SENT
        except RetryAfter as e:
            # Told exactly how long to wait: wait, then give this user
            # another try rather than dropping them for being unlucky.
            logger.warning(
                f"Broadcast: rate limited, sleeping {e.retry_after}s "
                f"(attempt {attempt}, recipient {user_id})"
            )
            if attempt == SEND_ATTEMPTS:
                return FAILED
            await asyncio.sleep(e.retry_after + 1)
        except Forbidden:
            await _opt_out(user_id)
            return BLOCKED
        except BadRequest as e:
            # "Chat not found" is the deleted-account twin of Forbidden:
            # there is nobody there, and no number of retries changes that.
            if "chat not found" in str(e).lower():
                await _opt_out(user_id)
                return BLOCKED
            logger.warning(f"Broadcast: Telegram refused {user_id}: {e}")
            return FAILED
        except NetworkError as e:
            # TimedOut is a NetworkError, so both land here.
            logger.warning(f"Broadcast: network error for {user_id}: {e}")
            if attempt == SEND_ATTEMPTS:
                return FAILED
            await asyncio.sleep(2 * attempt)
        except Exception as e:
            logger.warning(f"Broadcast: failed for {user_id}: {e}")
            return FAILED
    return FAILED


async def run(
    send: Callable[[int], Awaitable[Any]],
    *,
    limit: int | None = None,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> BroadcastReport:
    """Send to everyone, one at a time, and say what happened.

    No single recipient may end the run. An exception escaping the loop
    leaves the rest of the list with nothing *and* whoever started it with
    no report, which is the worst of both: they cannot tell who got it.
    """
    people = await recipients()
    if limit is not None:
        people = people[:limit]

    report = BroadcastReport(total=len(people))
    logger.info(f"Broadcast: starting, {report.total} recipients")

    for done, (user_id, name) in enumerate(people, start=1):
        try:
            status = await deliver(send, user_id)
        except Exception as e:
            logger.exception(f"Broadcast: unexpected failure for {user_id} ({name}): {e}")
            status = FAILED

        if status == SENT:
            report.sent += 1
        elif status == BLOCKED:
            report.blocked += 1
        else:
            report.failed.append(user_id)

        if on_progress and done % PROGRESS_EVERY == 0 and done < report.total:
            try:
                await on_progress(done, report.total)
            except Exception as e:
                logger.debug(f"Broadcast: progress update skipped: {e}")

        await asyncio.sleep(SECONDS_BETWEEN_SENDS)

    logger.info(
        f"Broadcast: done. {report.sent} sent, {report.blocked} blocked the bot, "
        f"{len(report.failed)} failed"
    )
    return report


def report_text(report: BroadcastReport) -> str:
    """The admin's receipt: counts, and the ids worth a manual message."""
    language = Language.RUSSIAN
    lines = [
        get_text('broadcast.report_title', language),
        get_text('broadcast.report_total', language, total=report.total),
        get_text('broadcast.report_sent', language, sent=report.sent),
        get_text('broadcast.report_blocked', language, blocked=report.blocked),
        get_text('broadcast.report_failed', language, failed=len(report.failed)),
    ]
    if report.failed:
        shown = ", ".join(str(i) for i in report.failed[:10])
        tail = " …" if len(report.failed) > 10 else ""
        lines.append("")
        lines.append(get_text('broadcast.report_ids', language, ids=f"{shown}{tail}"))
    return "\n".join(lines)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    language = Language.RUSSIAN
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text('broadcast.send_button', language), callback_data=CONFIRM
        ),
        InlineKeyboardButton(
            get_text('broadcast.cancel_button', language), callback_data=CANCEL
        ),
    ]])


async def _reply(query: Any, user_id: int, bot: Any, text: str) -> None:
    """Say something under the tapped card, wherever the card still is.

    `query.message` is an `InaccessibleMessage` once the card is older than
    48 hours — it has an id and nothing else, so replying to it is not a
    thing that exists. A broadcast confirmed a day later lands there, and
    the admin still has to get their receipt, so the fallback is an ordinary
    message to them.
    """
    if isinstance(query.message, Message):
        await query.message.reply_text(text)
    else:
        await bot.send_message(chat_id=user_id, text=text)


async def _replace(query: Any, user_id: int, bot: Any, text: str) -> None:
    """Collapse the tapped card into its outcome, or say it beneath."""
    try:
        await query.edit_message_text(text)
    except Exception as e:
        logger.warning(f"Broadcast: could not edit the preview card: {e}")
        await _reply(query, user_id, bot, text)


async def broadcast_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """`/broadcast`: ask the admin for the message to send.

    A non-admin gets silence rather than a refusal: there is nothing to be
    gained by confirming that the command exists.
    """
    message = update.message
    user = update.effective_user
    if message is None or user is None or context.user_data is None:
        return
    if not is_admin(user.id):
        logger.info(f"Broadcast: /broadcast from non-admin {user.id}, ignored")
        return

    context.user_data[_AWAITING] = True
    context.user_data.pop(_PREVIEW, None)
    await message.reply_text(get_text('broadcast.ask', Language.RUSSIAN))


async def broadcast_cancel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """`/cancel`: forget a broadcast that was being composed.

    Needed because the capture below stays armed until something disarms
    it: without this, an admin who typed `/broadcast` and then changed
    their mind would have their next ordinary message read as the draft.
    """
    message = update.message
    user = update.effective_user
    if message is None or user is None or context.user_data is None:
        return
    if not is_admin(user.id):
        return

    was_awaiting = bool(context.user_data.pop(_AWAITING, False))
    had_preview = context.user_data.pop(_PREVIEW, None) is not None
    key = 'broadcast.cancelled' if (was_awaiting or had_preview) \
        else 'broadcast.nothing_to_cancel'
    await message.reply_text(get_text(key, Language.RUSSIAN))


async def broadcast_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """The admin's next message after `/broadcast`: show it back, then ask.

    The draft is never re-typed or re-uploaded — the preview and every copy
    that follows are `copy_message` from this one, so what the admin sees is
    exactly what a recipient gets, whatever it is made of: text, a photo, a
    voice note, a video message.
    """
    message = update.message
    user = update.effective_user
    if message is None or user is None or context.user_data is None:
        return
    if not is_admin(user.id) or not context.user_data.get(_AWAITING):
        return

    try:
        total = len(await recipients())
    except Exception as e:
        # Reading the list is also the first step of sending it, so a
        # failure here is a failure of the whole thing. Say so now rather
        # than after the admin has confirmed.
        logger.error(f"Broadcast: could not read the recipient list: {e}")
        context.user_data.pop(_AWAITING, None)
        await message.reply_text(get_text('broadcast.error', Language.RUSSIAN))
        return

    context.user_data[_AWAITING] = False
    context.user_data[_PREVIEW] = (message.chat_id, message.message_id)

    await context.bot.copy_message(
        chat_id=message.chat_id,
        from_chat_id=message.chat_id,
        message_id=message.message_id,
        reply_markup=app_keyboard(),
    )
    await message.reply_text(
        get_text('broadcast.preview', Language.RUSSIAN, total=total),
        reply_markup=_confirm_keyboard(),
    )


async def broadcast_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """The two buttons under the preview.

    Registered ahead of the game's own callback handler and matched on a
    pattern, so nothing here ever reaches the callback registry — and with
    `block=False`, so a send to thousands of people does not hold up every
    other update for the minutes it takes.
    """
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or context.user_data is None:
        return

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Broadcast: could not answer the callback: {e}")

    if not is_admin(user.id):
        logger.warning(f"Broadcast: {query.data} from non-admin {user.id}, ignored")
        return

    language = Language.RUSSIAN
    bot = context.bot

    if query.data == CANCEL:
        context.user_data.pop(_AWAITING, None)
        context.user_data.pop(_PREVIEW, None)
        await _replace(query, user.id, bot, get_text('broadcast.cancelled', language))
        return

    preview = context.user_data.pop(_PREVIEW, None)
    if not preview:
        # `user_data` lives in the process. A redeploy between writing the
        # draft and tapping «Отправить» loses it, and without this the
        # button would sit there doing nothing at all — which reads as a
        # broadcast that silently did not go.
        await _replace(query, user.id, bot, get_text('broadcast.stale', language))
        return

    from_chat_id, message_id = preview
    context.user_data.pop(_AWAITING, None)
    await _replace(query, user.id, bot, get_text('broadcast.started', language))

    keyboard = app_keyboard()

    async def send(user_id: int) -> Any:
        return await bot.copy_message(
            chat_id=user_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )

    async def progress(done: int, total: int) -> None:
        await query.edit_message_text(
            get_text('broadcast.progress', language, done=done, total=total)
        )

    report = await run(send, on_progress=progress)
    await _reply(query, user.id, bot, report_text(report))
