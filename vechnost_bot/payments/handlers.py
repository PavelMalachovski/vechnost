"""Payment-related handlers for the Telegram bot."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..i18n import Language, get_text
from .middleware import check_and_register_user, get_payment_keyboard
from .services import user_has_access

logger = logging.getLogger(__name__)


async def handle_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«Проверить статус оплаты»: look the user up and say what was found.

    The callback query is *not* answered here. The only way in is the
    callback registry, and `handlers.handle_callback_query` has already
    answered it by the time this runs; Telegram rejects a second answer to
    the same query ("query is too old … or query ID is invalid"), and that
    BadRequest used to escape to the registry's catch-all, which replaced
    the paywall with «неизвестная команда». This is the one button a person
    who has just paid presses, so it must not be the one that breaks.
    """
    query = update.callback_query
    if not query:
        return

    if not update.effective_user:
        return

    # Register user
    await check_and_register_user(update, context)

    # Get user's language
    language = Language.RUSSIAN
    try:
        from ..storage import get_session

        session = await get_session(
            update.effective_chat.id if update.effective_chat else update.effective_user.id
        )
        language = Language.coerce(getattr(session, "language", None))
    except Exception as e:
        logger.warning(f"Could not get user language: {e}")

    # Show checking message
    checking_text = get_text("payment.checking", language)
    await query.edit_message_text(checking_text, parse_mode="HTML")

    # Check access
    has_access = await user_has_access(update.effective_user.id)

    if has_access:
        # User has access
        success_text = get_text("payment.access_granted", language)
        await query.edit_message_text(success_text, parse_mode="HTML")
    else:
        # No access
        no_access_text = get_text("payment.no_active_payment", language)
        keyboard = await get_payment_keyboard(language.value)
        await query.edit_message_text(
            no_access_text, parse_mode="HTML", reply_markup=keyboard
        )
