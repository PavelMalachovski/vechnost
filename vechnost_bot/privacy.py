"""`/delete_me`: everything the bot holds about a person, gone on request.

The product stores what a couple said about their sex life, money and
trust. There was a way to delete one test and one board, and a nightly
sweep for what nobody came back to, but no way to say "forget me": the
user row, the access, the rooms, the daily-push setting, all of it. This
is that way, and the right to it is not optional under the GDPR either.

Two steps, like a broadcast: the command explains what goes and shows a
button; the button does it. The confirm callback is registered ahead of
the game's catch-all with a pattern, so it never reaches the callback
registry, and it re-checks that the person tapping is the person whose
data it is - a button sits in a private chat, but a rule that costs
nothing is worth keeping.
"""

import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .i18n import Language, get_text

logger = logging.getLogger(__name__)

CONFIRM = "delete_me_confirm"
CANCEL = "delete_me_cancel"
CALLBACK_PATTERN = f"^({CONFIRM}|{CANCEL})$"


def _keyboard() -> InlineKeyboardMarkup:
    language = Language.RUSSIAN
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_text("privacy.confirm_button", language), callback_data=CONFIRM),
        InlineKeyboardButton(get_text("privacy.cancel_button", language), callback_data=CANCEL),
    ]])


async def erase_user(telegram_user_id: int) -> dict[str, int]:
    """Delete the person's rows and their bot session. Returns what went."""
    from .payments.database import get_db
    from .payments.repositories import UserRepository
    from .storage import delete_session

    async with get_db() as session:
        removed = await UserRepository.erase(session, telegram_user_id)
    # A private chat's id is the user's id; the session holds their deck
    # position and the 18+ flag.
    try:
        await delete_session(telegram_user_id)
    except Exception as e:
        logger.warning(f"Could not drop the bot session for {telegram_user_id}: {e}")
    return removed


async def delete_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/delete_me`: say what will go, and ask."""
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return
    await message.reply_text(
        get_text("privacy.ask", Language.RUSSIAN), reply_markup=_keyboard()
    )


async def delete_me_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The two buttons under the question."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"delete_me: could not answer the callback: {e}")

    language = Language.RUSSIAN
    tapper = query.from_user.id if query.from_user else None
    if tapper != user.id:
        logger.warning("delete_me: tap from someone other than the chat's user, ignored")
        return

    if query.data == CANCEL:
        await _replace(query, get_text("privacy.cancelled", language))
        return

    try:
        removed = await erase_user(user.id)
    except Exception as e:
        logger.error(f"delete_me failed for {user.id}: {e}", exc_info=True)
        await _replace(query, get_text("privacy.error", language))
        return

    key = "privacy.done" if removed.get("user") else "privacy.nothing"
    await _replace(query, get_text(key, language))


async def _replace(query: Any, text: str) -> None:
    """Collapse the question into its outcome, or say it beneath."""
    try:
        await query.edit_message_text(text)
    except Exception as e:
        logger.warning(f"delete_me: could not edit the question: {e}")
        if query.message is not None:
            await query.message.reply_text(text)
