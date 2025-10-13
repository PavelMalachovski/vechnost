"""Payment middleware for Telegram bot handlers."""

import logging
from functools import wraps
from typing import Callable, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..config import settings
from .services import user_has_access, get_products_for_purchase
from .database import get_db
from .repositories import UserRepository

logger = logging.getLogger(__name__)


def get_payment_required_message(language: str = "en") -> str:
    """Get payment required message in specified language."""
    messages = {
        "en": (
            "🔒 <b>Access Required</b>\n\n"
            "To use this bot, you need an active subscription or payment.\n\n"
            "Please choose one of the available options below:"
        ),
        "ru": (
            "🔒 <b>Требуется доступ</b>\n\n"
            "Для использования этого бота требуется активная подписка или оплата.\n\n"
            "Пожалуйста, выберите один из доступных вариантов ниже:"
        ),
        "cs": (
            "🔒 <b>Vyžadován přístup</b>\n\n"
            "Pro použití tohoto bota potřebujete aktivní předplatné nebo platbu.\n\n"
            "Prosím, vyberte jednu z dostupných možností níže:"
        ),
    }
    return messages.get(language, messages["en"])


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


def require_payment(handler: Callable) -> Callable:
    """
    Decorator to require payment for handler access.

    Usage:
        @require_payment
        async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # Handler code
    """

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Skip check if payments are disabled
        if not settings.enable_payment:
            return await handler(update, context)

        # Get user ID
        if not update.effective_user:
            logger.warning("No effective user in update")
            return

        telegram_user_id = update.effective_user.id

        # Register/update user in database
        try:
            async with get_db() as session:
                await UserRepository.create_or_update(
                    session,
                    telegram_user_id=telegram_user_id,
                    username=update.effective_user.username,
                    first_name=update.effective_user.first_name,
                    last_name=update.effective_user.last_name,
                )
        except Exception as e:
            logger.error(f"Error registering user: {e}")

        # Check if user has access
        has_access = await user_has_access(telegram_user_id)

        if not has_access:
            logger.info(f"User {telegram_user_id} denied access (no payment)")

            # Get user's language preference (from session or default to English)
            language = "en"
            try:
                from ..storage import get_session

                session = await get_session(update.effective_chat.id if update.effective_chat else telegram_user_id)
                language = session.language.value if hasattr(session, "language") else "en"
            except Exception as e:
                logger.warning(f"Could not get user language: {e}")

            # Send payment required message
            message = get_payment_required_message(language)
            keyboard = await get_payment_keyboard(language)

            if update.message:
                await update.message.reply_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )

            return

        # User has access, proceed with handler
        return await handler(update, context)

    return wrapper


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
            )
    except Exception as e:
        logger.error(f"Error registering user: {e}")

