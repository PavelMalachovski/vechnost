"""Handlers for payment and subscription management."""

import logging
import uuid
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from .config import settings
from .i18n import Language, get_text
from .monitoring import log_bot_event
from .payment_keyboards import (
    get_info_keyboard,
    get_payment_confirmation_keyboard,
    get_payment_plans_keyboard,
    get_premium_features_keyboard,
    get_subscription_keyboard,
    get_welcome_keyboard,
)
from .payment_models import (
    PaymentStatus,
    PaymentTransaction,
    SubscriptionTier,
    get_subscription_plan,
)
from .subscription_storage import get_subscription_storage
from .tribute_client import get_tribute_client

logger = logging.getLogger(__name__)


async def handle_enter_vechnost(query, session) -> None:
    """Handle 'Enter Vechnost' button - check access and start using the bot."""
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(query.from_user.id)

    # Check if user has access
    has_access = False

    if settings.payment_enabled:
        # Payment mode enabled - only premium users and whitelisted users have access
        username = query.from_user.username or ""

        # Check if user is whitelisted (for testing)
        if username in settings.whitelisted_usernames:
            logger.info(f"Whitelisted user @{username} granted access")
            has_access = True
        # Check if user has active premium subscription
        elif subscription.is_active() and subscription.tier != SubscriptionTier.FREE:
            logger.info(f"Premium user {query.from_user.id} granted access")
            has_access = True
        else:
            logger.info(f"User {query.from_user.id} (@{username}) requires subscription")
            has_access = False
    else:
        # Payment disabled - everyone has access
        logger.info(f"Payment disabled - granting access to user {query.from_user.id}")
        has_access = True

    if has_access:
        # User has access - show theme selection
        from .keyboards import get_theme_keyboard
        text = get_text('welcome.prompt', session.language)
        try:
            await query.edit_message_text(
                text,
                reply_markup=get_theme_keyboard(session.language)
            )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}, deleting and sending new")
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                text,
                reply_markup=get_theme_keyboard(session.language)
            )
    else:
        # User needs to subscribe
        text = get_text('subscription.premium_required', session.language)
        try:
            await query.edit_message_text(
                text,
                reply_markup=get_subscription_keyboard(subscription, session.language),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}, deleting and sending new")
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                text,
                reply_markup=get_subscription_keyboard(subscription, session.language),
                parse_mode="Markdown"
            )


async def handle_what_inside(query, session) -> None:
    """Handle 'What's inside?' button."""
    text = get_text('info.what_inside', session.language)

    try:
        await query.edit_message_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )
    except Exception as e:
        # If can't edit (e.g., it's a photo), delete and send new
        logger.warning(f"Could not edit message: {e}, deleting and sending new")
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )


async def handle_why_helps(query, session) -> None:
    """Handle 'Why Vechnost helps?' button."""
    text = get_text('info.why_helps', session.language)

    try:
        await query.edit_message_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}, deleting and sending new")
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )


async def handle_reviews(query, session) -> None:
    """Handle 'Reviews' button."""
    text = get_text('info.reviews', session.language)

    try:
        await query.edit_message_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}, deleting and sending new")
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )


async def handle_guarantee(query, session) -> None:
    """Handle 'Guarantee' button."""
    text = get_text('info.guarantee', session.language)

    try:
        await query.edit_message_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}, deleting and sending new")
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text(
            text,
            reply_markup=get_info_keyboard("back:welcome", session.language),
            parse_mode="Markdown"
        )


async def handle_subscription_status(query, session) -> None:
    """Handle subscription status display."""
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(query.from_user.id)

    # Build status message
    plan = get_subscription_plan(subscription.tier)

    if subscription.tier == SubscriptionTier.FREE:
        text = get_text('subscription.free_status', session.language)
    else:
        if subscription.is_active():
            days = subscription.days_remaining()
            text = get_text('subscription.premium_status_active', session.language).format(
                plan_name=plan.name,
                days=days,
                expires_at=subscription.expires_at.strftime("%d.%m.%Y") if subscription.expires_at else "—"
            )
        else:
            text = get_text('subscription.premium_status_expired', session.language).format(
                expires_at=subscription.expires_at.strftime("%d.%m.%Y") if subscription.expires_at else "—"
            )

    await query.edit_message_text(
        text,
        reply_markup=get_subscription_keyboard(subscription, session.language),
        parse_mode="Markdown"
    )


async def handle_subscription_upgrade(query, session) -> None:
    """Handle subscription upgrade request."""
    text = get_text('payment.select_plan', session.language)

    await query.edit_message_text(
        text,
        reply_markup=get_payment_plans_keyboard(session.language),
        parse_mode="Markdown"
    )


async def handle_payment_plan_selection(query, session, plan_type: str) -> None:
    """
    Handle payment plan selection.

    Args:
        query: Callback query
        session: Session state
        plan_type: 'monthly' or 'yearly'
    """
    if not settings.payment_enabled:
        await query.answer(
            get_text('payment.disabled', session.language),
            show_alert=True
        )
        return

    user_id = query.from_user.id

    # Determine amount and duration
    if plan_type == "monthly":
        amount = 299.0
        duration_days = 30
        description = get_text('payment.monthly_plan', session.language)
    else:  # yearly
        amount = 2990.0
        duration_days = 365
        description = get_text('payment.yearly_plan', session.language)

    # Create payment transaction
    transaction_id = f"txn_{user_id}_{uuid.uuid4().hex[:8]}"

    payment = PaymentTransaction(
        transaction_id=transaction_id,
        user_id=user_id,
        amount=amount,
        currency="RUB",
        subscription_tier=SubscriptionTier.PREMIUM,
        duration_days=duration_days,
        status=PaymentStatus.PENDING,
        metadata={
            "plan_type": plan_type,
            "user_id": user_id,
            "username": query.from_user.username,
        }
    )

    # Save payment
    storage = get_subscription_storage()
    await storage.save_payment(payment)

    try:
        # Create payment link via Tribute
        tribute = get_tribute_client()

        payment_link = await tribute.create_payment_link(
            amount=amount,
            currency="RUB",
            description=f"Vechnost Premium - {description}",
            user_id=user_id,
            metadata={
                "transaction_id": transaction_id,
                "plan_type": plan_type,
            },
            return_url=f"https://t.me/{(await query.get_bot()).username}?start=payment_{transaction_id}"
        )

        # Update payment with Tribute ID
        payment.tribute_payment_id = payment_link.payment_id
        await storage.save_payment(payment)

        # Show payment confirmation
        text = get_text('payment.created', session.language).format(
            amount=amount,
            description=description
        )

        await query.edit_message_text(
            text,
            reply_markup=get_payment_confirmation_keyboard(
                payment_link.payment_url,
                session.language
            ),
            parse_mode="Markdown"
        )

        log_bot_event(
            "payment_created",
            user_id=user_id,
            amount=amount,
            plan_type=plan_type,
            transaction_id=transaction_id
        )

    except Exception as e:
        logger.error(f"Failed to create payment: {e}", exc_info=True)

        # Mark payment as failed
        payment.mark_failed()
        await storage.save_payment(payment)

        await query.answer(
            get_text('payment.error', session.language),
            show_alert=True
        )


async def handle_payment_check(query, session) -> None:
    """Handle payment status check."""
    user_id = query.from_user.id
    storage = get_subscription_storage()

    # Get user's latest payment
    payments = await storage.get_user_payments(user_id)

    if not payments:
        await query.answer(
            get_text('payment.no_payments', session.language),
            show_alert=True
        )
        return

    # Check latest pending payment
    latest_payment = None
    for payment in payments:
        if payment.status == PaymentStatus.PENDING:
            latest_payment = payment
            break

    if not latest_payment:
        await query.answer(
            get_text('payment.no_pending', session.language),
            show_alert=True
        )
        return

    try:
        # Check status with Tribute
        tribute = get_tribute_client()

        if latest_payment.tribute_payment_id:
            status = await tribute.get_payment_status(latest_payment.tribute_payment_id)

            if status.status == "completed":
                # Payment completed - upgrade subscription
                latest_payment.mark_completed()
                await storage.save_payment(latest_payment)

                subscription = await storage.upgrade_subscription(
                    user_id=user_id,
                    tier=SubscriptionTier.PREMIUM,
                    duration_days=latest_payment.duration_days,
                    payment_id=latest_payment.transaction_id
                )

                # Success message
                text = get_text('payment.success', session.language).format(
                    days=subscription.days_remaining()
                )

                await query.edit_message_text(
                    text,
                    reply_markup=get_subscription_keyboard(subscription, session.language),
                    parse_mode="Markdown"
                )

                log_bot_event(
                    "payment_completed",
                    user_id=user_id,
                    transaction_id=latest_payment.transaction_id
                )

                # Send premium channel invite if available
                if settings.premium_channel_invite_link and not subscription.premium_channel_invite_sent:
                    try:
                        await query.message.reply_text(
                            get_text('subscription.premium_channel_welcome', session.language),
                            reply_markup=get_info_keyboard("back:main", session.language)
                        )
                        subscription.premium_channel_invite_sent = True
                        await storage.save_subscription(subscription)
                    except Exception as e:
                        logger.warning(f"Failed to send premium channel invite: {e}")

            elif status.status in ["failed", "cancelled"]:
                # Payment failed
                latest_payment.status = PaymentStatus.FAILED
                await storage.save_payment(latest_payment)

                await query.answer(
                    get_text('payment.failed', session.language),
                    show_alert=True
                )
            else:
                # Still pending
                await query.answer(
                    get_text('payment.pending', session.language),
                    show_alert=True
                )
        else:
            await query.answer(
                get_text('payment.error', session.language),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Failed to check payment status: {e}", exc_info=True)
        await query.answer(
            get_text('payment.error', session.language),
            show_alert=True
        )


async def handle_payment_cancel(query, session) -> None:
    """Handle payment cancellation."""
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(query.from_user.id)

    text = get_text('payment.cancelled', session.language)

    await query.edit_message_text(
        text,
        reply_markup=get_subscription_keyboard(subscription, session.language)
    )


async def handle_back_to_welcome(query, session) -> None:
    """Handle back to welcome screen."""
    text = get_text('welcome.main', session.language)

    try:
        await query.edit_message_text(
            text,
            reply_markup=get_welcome_keyboard(session.language),
            parse_mode="Markdown"
        )
    except Exception:
        # If we can't edit (e.g., it's a photo), delete and send new
        await query.message.delete()
        await query.message.reply_text(
            text,
            reply_markup=get_welcome_keyboard(session.language),
            parse_mode="Markdown"
        )


async def handle_back_to_subscription(query, session) -> None:
    """Handle back to subscription screen."""
    storage = get_subscription_storage()
    subscription = await storage.get_subscription(query.from_user.id)

    await handle_subscription_status(query, session)

