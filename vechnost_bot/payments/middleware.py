"""Payment middleware for Telegram bot handlers."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..config import settings
from .database import get_db
from .repositories import UserRepository
from .services import get_products_for_purchase

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


async def get_payment_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    """
    Generate payment keyboard with product links.

    Args:
        language: User's language preference

    Returns:
        InlineKeyboardMarkup with payment options
    """
    products = await get_products_for_purchase()
    keyboard = []

    # Add product buttons
    for product in products:
        # Prefer Telegram link, fallback to web link
        link = product.t_link or product.web_link
        if link:
            button_text = f"💎 {product.name}"
            keyboard.append([InlineKeyboardButton(button_text, url=link)])

    # If no products, add fallback Tribute link
    if not keyboard:
        texts = get_payment_keyboard_text(language)
        # Fallback to configured Tribute payment URL
        keyboard.append(
            [InlineKeyboardButton(texts["purchase"], url=settings.tribute_payment_url)]
        )

    # Add check status button
    texts = get_payment_keyboard_text(language)
    keyboard.append(
        [InlineKeyboardButton(texts["check_status"], callback_data="check_payment")]
    )

    return InlineKeyboardMarkup(keyboard)


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
            )
    except Exception as e:
        logger.error(f"Error registering user: {e}")

