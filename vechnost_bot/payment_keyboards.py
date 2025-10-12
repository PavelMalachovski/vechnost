"""Keyboards for payment and subscription management."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .config import settings
from .i18n import Language, get_text
from .payment_models import SubscriptionTier, UserSubscription, get_subscription_plan


def get_welcome_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """
    Get main welcome keyboard.

    Buttons:
    - ENTER VECHNOST
    - WHAT'S INSIDE?
    - WHY VECHNOST HELPS?
    - Contact Author (if configured)
    """
    keyboard = [
        [InlineKeyboardButton(
            get_text('welcome.enter_vechnost', language),
            callback_data="enter_vechnost"
        )],
        [InlineKeyboardButton(
            get_text('welcome.what_inside', language),
            callback_data="what_inside"
        )],
        [InlineKeyboardButton(
            get_text('welcome.why_helps', language),
            callback_data="why_helps"
        )],
    ]

    # Add contact button at the bottom if configured
    if settings.author_username:
        keyboard.append([InlineKeyboardButton(
            get_text('welcome.contact_author', language),
            url=f"https://t.me/{settings.author_username.lstrip('@')}"
        )])

    return InlineKeyboardMarkup(keyboard)


def get_subscription_keyboard(
    subscription: UserSubscription,
    language: Language = Language.RUSSIAN
) -> InlineKeyboardMarkup:
    """Get keyboard for subscription management."""
    keyboard = []

    if subscription.tier == SubscriptionTier.FREE:
        # Free tier: show upgrade options
        keyboard.append([InlineKeyboardButton(
            get_text('subscription.upgrade_premium', language),
            callback_data="subscription_upgrade_premium"
        )])
    else:
        # Premium tier: show status and manage
        if subscription.is_active():
            days = subscription.days_remaining()
            keyboard.append([InlineKeyboardButton(
                get_text('subscription.status_active', language).format(days=days),
                callback_data="subscription_status"
            )])

            # Premium channel access
            if settings.premium_channel_invite_link:
                keyboard.append([InlineKeyboardButton(
                    get_text('subscription.join_premium_channel', language),
                    url=settings.premium_channel_invite_link
                )])

            # Manage subscription
            if subscription.auto_renew:
                keyboard.append([InlineKeyboardButton(
                    get_text('subscription.cancel_auto_renew', language),
                    callback_data="subscription_cancel_auto_renew"
                )])
            else:
                keyboard.append([InlineKeyboardButton(
                    get_text('subscription.enable_auto_renew', language),
                    callback_data="subscription_enable_auto_renew"
                )])
        else:
            # Expired
            keyboard.append([InlineKeyboardButton(
                get_text('subscription.status_expired', language),
                callback_data="subscription_status"
            )])
            keyboard.append([InlineKeyboardButton(
                get_text('subscription.renew_premium', language),
                callback_data="subscription_upgrade_premium"
            )])

    # Back button
    keyboard.append([InlineKeyboardButton(
        get_text('navigation.back', language),
        callback_data="back:main"
    )])

    return InlineKeyboardMarkup(keyboard)


def get_payment_plans_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for selecting payment plan."""
    keyboard = [
        [InlineKeyboardButton(
            f"💳 {get_text('payment.monthly_plan', language)} - 299 ₽/мес",
            callback_data="payment_plan_monthly"
        )],
        [InlineKeyboardButton(
            f"💎 {get_text('payment.yearly_plan', language)} - 2990 ₽/год",
            callback_data="payment_plan_yearly"
        )],
        [InlineKeyboardButton(
            get_text('navigation.back', language),
            callback_data="back:subscription"
        )],
    ]

    return InlineKeyboardMarkup(keyboard)


def get_payment_confirmation_keyboard(
    payment_url: str,
    language: Language = Language.RUSSIAN
) -> InlineKeyboardMarkup:
    """Get keyboard for payment confirmation."""
    keyboard = [
        [InlineKeyboardButton(
            get_text('payment.pay_button', language),
            url=payment_url
        )],
        [InlineKeyboardButton(
            get_text('payment.check_payment', language),
            callback_data="payment_check"
        )],
        [InlineKeyboardButton(
            get_text('navigation.cancel', language),
            callback_data="payment_cancel"
        )],
    ]

    return InlineKeyboardMarkup(keyboard)


def get_premium_features_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard showing premium features."""
    keyboard = [
        [InlineKeyboardButton(
            get_text('subscription.get_premium', language),
            callback_data="subscription_upgrade_premium"
        )],
        [InlineKeyboardButton(
            get_text('navigation.back', language),
            callback_data="back:main"
        )],
    ]

    return InlineKeyboardMarkup(keyboard)


def get_info_keyboard(
    callback_back: str = "back:main",
    language: Language = Language.RUSSIAN
) -> InlineKeyboardMarkup:
    """Get keyboard for info pages."""
    keyboard = [
        [InlineKeyboardButton(
            get_text('navigation.back', language),
            callback_data=callback_back
        )],
    ]

    return InlineKeyboardMarkup(keyboard)

