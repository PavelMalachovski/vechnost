"""Payment-related handlers for the Telegram bot."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..i18n import get_text
from .services import user_has_access
from .middleware import get_payment_keyboard, check_and_register_user

logger = logging.getLogger(__name__)


async def handle_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle check payment status callback."""
    query = update.callback_query
    if not query:
        return

    await query.answer()

    if not update.effective_user:
        return

    # Register user
    await check_and_register_user(update, context)

    # Get user's language
    language = "en"
    try:
        from ..storage import get_session

        session = await get_session(
            update.effective_chat.id if update.effective_chat else update.effective_user.id
        )
        language = session.language.value if hasattr(session, "language") else "en"
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
        keyboard = await get_payment_keyboard(language)
        await query.edit_message_text(
            no_access_text, parse_mode="HTML", reply_markup=keyboard
        )

