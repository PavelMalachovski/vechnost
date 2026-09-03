"""Service layer for payment operations."""

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..config import settings
from .database import get_db
from .gifts import (
    create_gift_certificate,
    deliver_gift_certificate,
    gift_language,
    is_gift_purchase,
)
from .models import Product
from .repositories import (
    CertificateRepository,
    PaymentRepository,
    ProductRepository,
    SubscriptionRepository,
    UserRepository,
    WebhookEventRepository,
)
from .signature import (
    compute_body_sha256,
    signature_header,
    verify_tribute_signature,
)
from .tribute_client import TributeAPIError, TributeClient
from .tribute_event import TributeEvent

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


def _error(message: str, code: int) -> dict[str, Any]:
    return {"status": "error", "message": message, "code": code}


async def apply_webhook_event(
    payload: dict[str, Any],
    headers: Mapping[str, str],
    raw_body: bytes,
) -> dict[str, Any]:
    """Apply one Tribute delivery to the buyer's access.

    The order here is the whole point. The signature is checked before
    anything touches the database: a delivery that fails it is answered
    401 and leaves no trace, so Tribute's retry of the same body (they
    retry for about a day) is judged on its own merits. The version this
    replaces recorded the rejection under the body's hash first, so the
    retry, correctly signed, was told "already processed" and the payment
    was lost for good.

    What the event *does* is decided by `tribute_event.action_for`, a
    table: grant, revoke, or ignore. A `payments` row is written for every
    grant and revoke as a journal, and only as a journal - access is read
    from `subscriptions`, never inferred from the existence of a payment.

    Returns a dict with `status`, `message` and, on failure, an HTTP `code`.
    """
    if not verify_tribute_signature(headers, raw_body):
        return _error("Invalid webhook signature", 401)

    try:
        event = TributeEvent.parse(payload)
    except ValueError as e:
        return _error(str(e), 400)

    if event.is_test:
        logger.info("Test webhook received from Tribute")
        return {
            "status": "success",
            "message": "Test webhook received successfully",
            "code": 200,
        }
    if not event.name:
        logger.warning(f"Webhook without an event name: {list(payload)}")
        return _error("Missing event name in payload", 400)

    try:
        telegram_user_id = event.telegram_user_id
    except ValueError:
        logger.error("Non-numeric telegram_user_id in webhook payload")
        return _error("telegram_user_id is not a number", 400)
    if not telegram_user_id:
        logger.error(f"Webhook {event.name} without a telegram_user_id")
        return _error("Missing telegram_user_id in payload", 400)

    body_sha256 = compute_body_sha256(raw_body)
    action = event.action
    now = datetime.utcnow()

    try:
        async with get_db() as session:
            existing = await WebhookEventRepository.get_by_body_sha256(
                session, body_sha256
            )
            if existing:
                logger.info(f"Webhook already processed: {body_sha256[:12]}")
                return {
                    "status": "success",
                    "message": "Webhook already processed (idempotent)",
                    "webhook_event_id": existing.id,
                }

            user = await UserRepository.create_or_update(
                session,
                telegram_user_id=telegram_user_id,
                username=event.username,
                first_name=event.first_name,
                last_name=event.last_name,
            )

            payment_id: int | None = None
            if action != "ignore":
                payment = await PaymentRepository.get_by_body_sha256(session, body_sha256)
                if payment is None:
                    payment = await PaymentRepository.create(
                        session,
                        provider="tribute",
                        event_name=event.name,
                        user_id=user.id,
                        telegram_user_id=user.telegram_user_id,
                        product_id=None,
                        amount=event.amount,
                        currency=event.currency,
                        expires_at=event.expires_at,
                        raw_body=payload,
                        signature=signature_header(headers) or "",
                        body_sha256=body_sha256,
                    )
                payment_id = payment.id

            note: str | None = None
            if action == "grant" and is_gift_purchase(event.product_id):
                # A present: the buyer gets a certificate to hand on, not
                # access of their own.
                gift_code = await create_gift_certificate(session)
                note = "gift certificate issued"
                logger.info(f"Gift purchase by {telegram_user_id}: certificate issued")
                try:
                    await deliver_gift_certificate(
                        telegram_user_id, gift_code, gift_language(user.language)
                    )
                except Exception as e:
                    # The certificate exists either way; support can recover
                    # the code from the certificates table.
                    logger.error(f"Failed to deliver gift certificate: {e}")
            elif action == "grant":
                await SubscriptionRepository.upsert(
                    session,
                    user_id=user.id,
                    subscription_id=event.access_key,
                    period=event.period,
                    status="active",
                    expires_at=event.expires_at,
                    last_event_at=now,
                )
                logger.info(
                    f"Access granted to {telegram_user_id} by {event.name}: "
                    f"period={event.period}, expires_at={event.expires_at}"
                )
            elif action == "revoke":
                revoked = await SubscriptionRepository.revoke_for_user(
                    session,
                    user.id,
                    subscription_id=event.access_key or None,
                    status="refunded" if "refund" in event.name.lower() else "canceled",
                    when=now,
                )
                note = f"revoked {revoked}"
                logger.info(
                    f"Access revoked for {telegram_user_id} by {event.name}: "
                    f"{revoked} row(s)"
                )
            else:
                note = "ignored: unknown event"
                logger.warning(
                    f"Webhook {event.name!r} is not an event this code knows; "
                    "acknowledged and left without effect"
                )

            await WebhookEventRepository.create(
                session,
                name=event.name,
                sent_at=event.sent_at or event.created_at or now,
                body_sha256=body_sha256,
                status_code=200,
                processed_at=now,
                error=note,
            )

            return {
                "status": "success",
                "message": "Webhook processed successfully",
                "action": action,
                "payment_id": payment_id,
            }

    except IntegrityError as e:
        # The same body landing twice at once: one of them wrote the row.
        logger.error(f"Database integrity error processing webhook: {e}")
        return {
            "status": "success",
            "message": "Webhook already processed (race condition)",
        }
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return _error("internal error", 500)


async def user_has_access(telegram_user_id: int) -> bool:
    """Whether this user may see paid content.

    Access is an active, unexpired row in `subscriptions` (a lifetime
    purchase is one with no expiry), or an activated certificate, or
    payments being switched off altogether. A row in `payments` is a
    journal entry and counts for nothing on its own: it used to, and every
    event Tribute sent - a cancellation included - became lifetime access.
    """
    if not settings.enable_payment:
        return True

    try:
        async with get_db() as session:
            user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
            if not user:
                logger.debug(
                    f"User {telegram_user_id} not found in database - no access"
                )
                return False

            subscriptions = await SubscriptionRepository.get_active_subscriptions_for_user(
                session, user.id
            )
            if subscriptions:
                logger.debug(
                    f"User {telegram_user_id} has {len(subscriptions)} active subscription(s)"
                )
                return True

            certificates = await CertificateRepository.get_by_user(
                session, telegram_user_id
            )
            if certificates:
                logger.debug(
                    f"User {telegram_user_id} has {len(certificates)} activated certificate(s)"
                )
                return True

            logger.debug(f"User {telegram_user_id} has no active access")
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


CURRENCY_SYMBOLS = {"eur": "€", "usd": "$", "rub": "₽", "czk": "Kč", "gbp": "£"}


def format_price(amount_cents: int, currency: str) -> str:
    """Human-readable price, e.g. 499 + 'eur' -> '4,99 €'."""
    value = amount_cents / 100
    text = f"{value:.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    text = text.replace(".", ",")
    symbol = CURRENCY_SYMBOLS.get(currency.lower(), currency.upper())
    return f"{text} {symbol}"


async def get_price_label() -> str | None:
    """Formatted price of the cheapest product, or None if none are synced."""
    products = await get_products_for_purchase()
    for product in products:
        if product.amount:
            return format_price(product.amount, product.currency or "eur")
    return None


async def activate_certificate(
    code: str,
    telegram_user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, Any]:
    """
    Activate a certificate code for a user.

    Args:
        code: Certificate code from QR
        telegram_user_id: Telegram user ID activating the certificate
        username: Telegram username (optional)
        first_name: User first name (optional)
        last_name: User last name (optional)

    Returns:
        Dict with activation result
    """
    try:
        async with get_db() as session:
            # Find certificate
            certificate = await CertificateRepository.get_by_code(session, code)
            if not certificate:
                logger.warning("Certificate activation attempted with an unknown code")
                return {
                    "status": "error",
                    "message": "Certificate not found",
                    "code": 404,
                }

            # Check if already used (one-time use enforcement)
            if certificate.is_used:
                logger.warning(
                    f"Certificate #{certificate.id} already used at {certificate.used_at}"
                )
                return {
                    "status": "error",
                    "message": "Certificate already used",
                    "code": 409,
                }

            # Ensure user exists with full information
            await UserRepository.create_or_update(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

            # Mark certificate as used (one-time use)
            await CertificateRepository.mark_as_used(
                session, certificate, telegram_user_id
            )

            await session.commit()

            # Verify certificate was marked as used
            await session.refresh(certificate)
            logger.info(
                f"Activated certificate #{certificate.id} for user {telegram_user_id} "
                f"(is_used: {certificate.is_used})"
            )

            return {
                "status": "success",
                "message": "Certificate activated successfully",
                "certificate_id": certificate.id,
            }

    except Exception as e:
        logger.error(f"Error activating certificate: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "internal error",
            "code": 500,
        }
