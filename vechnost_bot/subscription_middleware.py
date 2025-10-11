"""Middleware for subscription access control."""

import logging
from typing import Any, Callable

from telegram import Update

from .config import settings
from .i18n import get_text
from .models import Theme
from .payment_keyboards import get_premium_features_keyboard
from .payment_models import SubscriptionTier
from .subscription_storage import get_subscription_storage

logger = logging.getLogger(__name__)


async def check_premium_access(
    user_id: int,
    theme: Theme | None = None,
) -> tuple[bool, str | None]:
    """
    Check if user has access to premium content.

    Args:
        user_id: Telegram user ID
        theme: Theme to check access for

    Returns:
        Tuple of (has_access, error_message)
    """
    # If payments are disabled, grant access to everyone
    if not settings.payment_enabled:
        return True, None

    storage = get_subscription_storage()
    subscription = await storage.get_subscription(user_id)

    # Check if subscription is active
    if not subscription.is_active():
        return False, "subscription_expired"

    # Free tier checks
    if subscription.tier == SubscriptionTier.FREE:
        # Check daily limit
        if not subscription.can_ask_question_today():
            return False, "daily_limit_reached"

        # Check premium theme access
        if theme in [Theme.SEX, Theme.PROVOCATION]:
            return False, "premium_theme_required"

    return True, None


async def check_and_enforce_subscription(
    query: Any,
    session: Any,
    theme: Theme | None = None,
) -> bool:
    """
    Check subscription and show upgrade prompt if needed.

    Args:
        query: Callback query
        session: Session state
        theme: Theme to check access for

    Returns:
        True if user has access, False otherwise
    """
    user_id = query.from_user.id
    has_access, error = await check_premium_access(user_id, theme)

    if has_access:
        return True

    # Show appropriate error message
    if error == "subscription_expired":
        message = get_text('subscription.expired_prompt', session.language)
    elif error == "daily_limit_reached":
        message = get_text('subscription.daily_limit_prompt', session.language)
    elif error == "premium_theme_required":
        message = get_text('subscription.premium_theme_prompt', session.language)
    else:
        message = get_text('subscription.upgrade_required', session.language)

    try:
        await query.edit_message_text(
            message,
            reply_markup=get_premium_features_keyboard(session.language),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Failed to send upgrade prompt: {e}")
        await query.answer(message, show_alert=True)

    return False


async def increment_question_count(user_id: int) -> None:
    """
    Increment user's daily question count.

    Args:
        user_id: Telegram user ID
    """
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(user_id)

    # Only increment for free tier
    if subscription.tier == SubscriptionTier.FREE:
        subscription.increment_question_count()
        await storage.save_subscription(subscription)

