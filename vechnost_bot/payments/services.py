"""Service layer for payment operations."""

import logging
from datetime import datetime
from typing import Mapping, Dict, Any, Optional

from sqlalchemy.exc import IntegrityError

from ..config import settings
from .database import get_db
from .models import User, Product, Payment, Subscription, WebhookEvent
from .repositories import (
    UserRepository,
    ProductRepository,
    PaymentRepository,
    SubscriptionRepository,
    WebhookEventRepository,
)
from .tribute_client import TributeClient, TributeAPIError
from .signature import compute_body_sha256, verify_tribute_signature

logger = logging.getLogger(__name__)


async def sync_products_from_tribute() -> int:
    """
    Synchronize products from Tribute API.

    Returns:
        Number of products synced
    """
    try:
        client = TributeClient()
        products = await client.list_products()

        count = 0
        async with get_db() as session:
            for product_data in products:
                await ProductRepository.upsert(
                    session,
                    product_id=product_data.id,
                    type=product_data.type,
                    name=product_data.name,
                    amount=product_data.amount,
                    currency=product_data.currency,
                    stars_amount=product_data.stars_amount,
                    t_link=product_data.t_link,
                    web_link=product_data.web_link,
                )
                count += 1

        logger.info(f"Synced {count} products from Tribute")
        return count

    except TributeAPIError as e:
        logger.error(f"Failed to sync products: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error syncing products: {e}")
        raise


async def apply_webhook_event(
    payload: Dict[str, Any],
    headers: Mapping[str, str],
    raw_body: bytes,
) -> Dict[str, Any]:
    """
    Process incoming webhook event from Tribute.

    Args:
        payload: Parsed JSON payload
        headers: Request headers
        raw_body: Raw request body bytes

    Returns:
        Dict with processing result
    """
    # Compute body hash for idempotency
    body_sha256 = compute_body_sha256(raw_body)

    try:
        async with get_db() as session:
            # Check if webhook was already processed (idempotency)
            existing_webhook = await WebhookEventRepository.get_by_body_sha256(
                session, body_sha256
            )
            if existing_webhook:
                logger.info(f"Webhook already processed: {body_sha256}")
                return {
                    "status": "success",
                    "message": "Webhook already processed (idempotent)",
                    "webhook_event_id": existing_webhook.id,
                }

            # Check if payment with same body already exists
            existing_payment = await PaymentRepository.get_by_body_sha256(
                session, body_sha256
            )
            if existing_payment:
                logger.info(f"Payment already exists for body: {body_sha256}")
                return {
                    "status": "success",
                    "message": "Payment already processed (idempotent)",
                    "payment_id": existing_payment.id,
                }

            # Verify signature
            signature_header = (
                headers.get("X-Tribute-Signature")
                or headers.get("x-tribute-signature")
                or ""
            )

            if not verify_tribute_signature(headers, raw_body):
                error_msg = "Invalid webhook signature"
                logger.warning(error_msg)

                # Log failed webhook attempt
                await WebhookEventRepository.create(
                    session,
                    name=payload.get("event_name", "unknown"),
                    sent_at=datetime.utcnow(),
                    body_sha256=body_sha256,
                    status_code=401,
                    error=error_msg,
                )

                return {
                    "status": "error",
                    "message": error_msg,
                    "code": 401,
                }

            # Extract event data
            event_name = payload.get("event_name") or payload.get("event") or payload.get("type")
            if not event_name:
                error_msg = "Missing event_name in payload"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg, "code": 400}

            # Extract user information
            # Adjust based on actual Tribute webhook structure
            telegram_user_id = (
                payload.get("telegram_user_id")
                or payload.get("customer", {}).get("telegram_user_id")
                or payload.get("metadata", {}).get("telegram_user_id")
            )

            if not telegram_user_id:
                error_msg = "Missing telegram_user_id in payload"
                logger.error(error_msg)

                # Log webhook with error
                await WebhookEventRepository.create(
                    session,
                    name=event_name,
                    sent_at=datetime.utcnow(),
                    body_sha256=body_sha256,
                    status_code=400,
                    error=error_msg,
                )

                return {"status": "error", "message": error_msg, "code": 400}

            # Ensure user exists
            user = await UserRepository.create_or_update(
                session,
                telegram_user_id=int(telegram_user_id),
                username=payload.get("username"),
                first_name=payload.get("first_name"),
                last_name=payload.get("last_name"),
            )

            # Extract payment information
            amount = payload.get("amount", 0)
            currency = payload.get("currency", "USD")
            product_id = payload.get("product_id")
            expires_at = None

            # Parse expires_at if provided
            expires_at_str = payload.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(
                        expires_at_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    logger.warning(f"Invalid expires_at format: {expires_at_str}")

            # Create payment record
            payment = await PaymentRepository.create(
                session,
                provider="tribute",
                event_name=event_name,
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
                product_id=product_id,
                amount=amount,
                currency=currency,
                expires_at=expires_at,
                raw_body=payload,
                signature=signature_header,
                body_sha256=body_sha256,
            )

            # Handle subscription events
            if "subscription" in event_name.lower():
                subscription_id = payload.get("subscription_id") or payload.get("id")
                if subscription_id:
                    status = "active"
                    if "cancel" in event_name.lower():
                        status = "canceled"
                    elif "expire" in event_name.lower():
                        status = "expired"
                    elif "renew" in event_name.lower():
                        status = "active"

                    period = payload.get("period", "month")

                    # Default expires_at to 30 days from now if not provided
                    if not expires_at:
                        from datetime import timedelta

                        expires_at = datetime.utcnow() + timedelta(days=30)

                    await SubscriptionRepository.upsert(
                        session,
                        user_id=user.id,
                        subscription_id=int(subscription_id),
                        period=period,
                        status=status,
                        expires_at=expires_at,
                        last_event_at=datetime.utcnow(),
                    )

            # Log successful webhook processing
            await WebhookEventRepository.create(
                session,
                name=event_name,
                sent_at=datetime.utcnow(),
                body_sha256=body_sha256,
                status_code=200,
                processed_at=datetime.utcnow(),
            )

            logger.info(
                f"Successfully processed webhook: {event_name} for user {telegram_user_id}"
            )

            return {
                "status": "success",
                "message": "Webhook processed successfully",
                "payment_id": payment.id,
            }

    except IntegrityError as e:
        logger.error(f"Database integrity error processing webhook: {e}")
        # Most likely a duplicate due to race condition
        return {
            "status": "success",
            "message": "Webhook already processed (race condition)",
        }
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Internal error: {str(e)}",
            "code": 500,
        }


async def user_has_access(telegram_user_id: int) -> bool:
    """
    Check if user has access based on payment/subscription status.

    Args:
        telegram_user_id: Telegram user ID

    Returns:
        True if user has access, False otherwise
    """
    # If payments are disabled, everyone has access
    if not settings.enable_payment:
        return True

    try:
        async with get_db() as session:
            # Get user
            user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
            if not user:
                # User not in system yet - no access
                return False

            # Check for active subscriptions
            subscriptions = await SubscriptionRepository.get_active_subscriptions_for_user(
                session, user.id
            )
            if subscriptions:
                logger.info(
                    f"User {telegram_user_id} has {len(subscriptions)} active subscription(s)"
                )
                return True

            # Check for active one-time payments with non-expired access
            payments = await PaymentRepository.get_active_payments_for_user(
                session, telegram_user_id
            )
            if payments:
                logger.info(
                    f"User {telegram_user_id} has {len(payments)} active payment(s)"
                )
                return True

            logger.info(f"User {telegram_user_id} has no active access")
            return False

    except Exception as e:
        logger.error(f"Error checking user access: {e}", exc_info=True)
        # On error, deny access by default (fail-safe)
        return False


async def get_products_for_purchase() -> list[Product]:
    """
    Get list of products available for purchase.

    Returns:
        List of products
    """
    try:
        async with get_db() as session:
            products = await ProductRepository.get_all(session)
            return products
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        return []

