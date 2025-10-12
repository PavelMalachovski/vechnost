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
    username: str | None = None,
    theme: Theme | None = None,
) -> tuple[bool, str | None]:
    """
    Check if user has access to content.

    New logic:
    - If payment_enabled=False: everyone has access
    - If payment_enabled=True: only premium subscribers and whitelisted users have access

    Args:
        user_id: Telegram user ID
        username: Telegram username (for whitelist check)
        theme: Theme to check access for (no longer used, kept for compatibility)

    Returns:
        Tuple of (has_access, error_message)
    """
    # If payments are disabled, grant access to everyone
    if not settings.payment_enabled:
        logger.debug(f"Payment disabled - granting access to user {user_id}")
        return True, None

    # Payment enabled - check whitelist and premium subscription
    username = username or ""

    # Check if user is whitelisted (for testing)
    if username in settings.whitelisted_usernames:
        logger.info(f"Whitelisted user @{username} granted access")
        return True, None

    # Check premium subscription
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(user_id)

    # Check if subscription is active and premium
    if subscription.is_active() and subscription.tier != SubscriptionTier.FREE:
        logger.debug(f"Premium user {user_id} granted access")
        return True, None

    # No access - subscription required
    logger.info(f"User {user_id} (@{username}) requires subscription")
    return False, "premium_required"


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
        theme: Theme to check access for (no longer used)

    Returns:
        True if user has access, False otherwise
    """
    user_id = query.from_user.id
    username = query.from_user.username
    has_access, error = await check_premium_access(user_id, username, theme)

    if has_access:
        return True

    # Show subscription required message
    message = get_text('subscription.premium_required', session.language)

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
    Deprecated: No longer needed with full payment model.

    Kept for compatibility but does nothing.

    Args:
        user_id: Telegram user ID
    """
    # No-op: daily limits removed in favor of full payment model
    pass

