"""Webhook handler for Tribute payment notifications."""

import logging
from typing import Any

from .config import settings
from .monitoring import log_bot_event
from .payment_models import PaymentStatus, SubscriptionTier
from .subscription_storage import get_subscription_storage
from .tribute_client import get_tribute_client

logger = logging.getLogger(__name__)


async def process_tribute_webhook(
    payload: dict[str, Any],
    signature: str | None = None
) -> dict[str, Any]:
    """
    Process Tribute webhook event.

    Args:
        payload: Webhook payload from Tribute
        signature: Signature from X-Tribute-Signature header

    Returns:
        Response dict with status
    """
    try:
        # Verify signature if provided
        if signature and settings.tribute_webhook_secret:
            tribute = get_tribute_client()

            import json
            payload_str = json.dumps(payload, separators=(',', ':'))

            if not tribute.verify_webhook_signature(payload_str, signature):
                logger.warning("Invalid webhook signature")
                return {
                    "status": "error",
                    "message": "Invalid signature"
                }

        # Parse webhook event
        event_type = payload.get("event_type")

        if not event_type:
            logger.warning("Webhook event missing event_type")
            return {
                "status": "error",
                "message": "Missing event_type"
            }

        # Route to appropriate handler
        if event_type == "payment.completed":
            return await handle_payment_completed(payload)
        elif event_type == "payment.failed":
            return await handle_payment_failed(payload)
        elif event_type == "subscription.renewed":
            return await handle_subscription_renewed(payload)
        elif event_type == "subscription.cancelled":
            return await handle_subscription_cancelled(payload)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
            return {
                "status": "ok",
                "message": f"Event {event_type} received but not processed"
            }

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


async def handle_payment_completed(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle payment.completed webhook event."""
    payment_id = payload.get("payment_id")
    metadata = payload.get("metadata", {})
    transaction_id = metadata.get("transaction_id")

    if not transaction_id:
        logger.warning(f"Payment {payment_id} missing transaction_id in metadata")
        return {
            "status": "error",
            "message": "Missing transaction_id"
        }

    storage = get_subscription_storage()

    # Get payment transaction
    payment = await storage.get_payment(transaction_id)

    if not payment:
        logger.warning(f"Payment transaction {transaction_id} not found")
        return {
            "status": "error",
            "message": "Transaction not found"
        }

    # Mark payment as completed
    payment.mark_completed()
    payment.tribute_payment_id = payment_id
    await storage.save_payment(payment)

    # Upgrade subscription
    subscription = await storage.upgrade_subscription(
        user_id=payment.user_id,
        tier=payment.subscription_tier,
        duration_days=payment.duration_days,
        payment_id=transaction_id
    )

    logger.info(
        f"Payment {transaction_id} completed for user {payment.user_id}, "
        f"upgraded to {payment.subscription_tier.value}"
    )

    log_bot_event(
        "payment_webhook_completed",
        user_id=payment.user_id,
        transaction_id=transaction_id,
        amount=payment.amount,
        tier=payment.subscription_tier.value
    )

    return {
        "status": "ok",
        "message": "Payment processed successfully"
    }


async def handle_payment_failed(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle payment.failed webhook event."""
    payment_id = payload.get("payment_id")
    metadata = payload.get("metadata", {})
    transaction_id = metadata.get("transaction_id")

    if not transaction_id:
        logger.warning(f"Failed payment {payment_id} missing transaction_id")
        return {
            "status": "ok",
            "message": "Transaction ID not found, skipping"
        }

    storage = get_subscription_storage()

    # Get payment transaction
    payment = await storage.get_payment(transaction_id)

    if payment:
        payment.mark_failed()
        await storage.save_payment(payment)

        logger.info(f"Payment {transaction_id} marked as failed")

        log_bot_event(
            "payment_webhook_failed",
            user_id=payment.user_id,
            transaction_id=transaction_id
        )

    return {
        "status": "ok",
        "message": "Payment failure recorded"
    }


async def handle_subscription_renewed(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle subscription.renewed webhook event."""
    subscription_id = payload.get("subscription_id")
    customer_id = payload.get("customer_id")
    metadata = payload.get("metadata", {})
    user_id = metadata.get("user_id")

    if not user_id:
        logger.warning(f"Subscription renewal {subscription_id} missing user_id")
        return {
            "status": "error",
            "message": "Missing user_id"
        }

    storage = get_subscription_storage()

    # Renew subscription (default 30 days)
    subscription = await storage.renew_subscription(
        user_id=int(user_id),
        duration_days=30,
        payment_id=subscription_id
    )

    logger.info(f"Subscription renewed for user {user_id}")

    log_bot_event(
        "subscription_webhook_renewed",
        user_id=user_id,
        subscription_id=subscription_id
    )

    return {
        "status": "ok",
        "message": "Subscription renewed successfully"
    }


async def handle_subscription_cancelled(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle subscription.cancelled webhook event."""
    subscription_id = payload.get("subscription_id")
    metadata = payload.get("metadata", {})
    user_id = metadata.get("user_id")

    if not user_id:
        logger.warning(f"Subscription cancellation {subscription_id} missing user_id")
        return {
            "status": "error",
            "message": "Missing user_id"
        }

    storage = get_subscription_storage()

    # Cancel auto-renewal
    subscription = await storage.cancel_subscription(int(user_id))

    logger.info(f"Subscription cancelled for user {user_id}")

    log_bot_event(
        "subscription_webhook_cancelled",
        user_id=user_id,
        subscription_id=subscription_id
    )

    return {
        "status": "ok",
        "message": "Subscription cancelled successfully"
    }

