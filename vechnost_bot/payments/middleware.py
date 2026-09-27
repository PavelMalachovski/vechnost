"""Payment middleware for Telegram bot handlers."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .database import get_db
from .repositories import UserRepository
from .services import purchase_url_for, user_is_referred

logger = logging.getLogger(__name__)


def get_payment_keyboard_text(language: str = "en") -> dict:
    """Get payment keyboard button texts in specified language."""
    texts = {
        "en": {
            "purchase": "💳 Purchase Access",
            "check_status": "🔄 Check Payment Status",
            "support": "💬 Contact Support",
        },
        "ru": {
            "purchase": "💳 Купить доступ",
            "check_status": "🔄 Проверить статус оплаты",
            "support": "💬 Связаться с поддержкой",
        },
        "cs": {
            "purchase": "💳 Zakoupit přístup",
            "check_status": "🔄 Zkontrolovat stav platby",
            "support": "💬 Kontaktovat podporu",
        },
    }
    return texts.get(language, texts["en"])


async def get_payment_keyboard(
    language: str = "en", telegram_user_id: int | None = None
) -> InlineKeyboardMarkup:
    """The paywall's two buttons: buy access, and check the payment.

    One purchase button, never one per synced product. The catalogue also
    holds the gift and the referral discount, and listing all of it offered
    both to everyone (backend audit B-10). The link is the Mini App's
    (`services.purchase_url_for`), so a user who came in on someone's invite
    - `telegram_user_id` says who is asking - gets the discounted page here
    as well.
    """
    referred = False
    if telegram_user_id:
        referred = await user_is_referred(telegram_user_id)
    texts = get_payment_keyboard_text(language)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(texts["purchase"], url=await purchase_url_for(referred))],
        [InlineKeyboardButton(texts["check_status"], callback_data="check_payment")],
    ])


async def check_and_register_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check and register user in the database.

    This should be called on first interaction with bot.
    """
    if not update.effective_user:
        return

    try:
        async with get_db() as session:
            await UserRepository.create_or_update(
                session,
                telegram_user_id=update.effective_user.id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name,
                language=update.effective_user.language_code,
                # They are talking to the bot, so it can talk back.
                can_message=True,
            )
    except Exception as e:
        logger.error(f"Error registering user: {e}")

