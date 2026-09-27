"""Service layer for payment operations."""

import logging
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import referrals
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
    CANCELED,
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
    signing_keys,
    verify_tribute_signature,
)
from .tribute_client import TributeAPIError, TributeClient
from .tribute_event import TributeEvent, revoked_status

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
    table: grant, cancel, revoke, or ignore. A `payments` row is written
    for every grant, cancellation and revocation as a journal, and only as
    a journal - access is read from `subscriptions`, never inferred from
    the existence of a payment.

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

    if not signing_keys():
        # Verification was skipped: payments are off and no key is set (with
        # payments on, verify_tribute_signature has already refused). There
        # is no paywall to protect now - but a grant recorded now is still a
        # subscription row the day payments are switched on, so anyone who
        # POSTed their own telegram_user_id before launch would launch as a
        # lifetime customer. Acknowledged, and nothing applied.
        logger.warning(f"Unsigned {event.name!r} acknowledged and not applied: no signing key")
        return {
            "status": "success",
            "message": "Unsigned delivery acknowledged and not applied (no signing key configured)",
            "action": "ignore",
            "code": 200,
        }

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
            elif action == "cancel":
                note = await _cancel(session, event, user.id, now)
                logger.info(f"{event.name} for {telegram_user_id}: {note}")
            elif action == "revoke":
                revoked = await SubscriptionRepository.revoke_for_user(
                    session,
                    user.id,
                    subscription_id=event.access_key or None,
                    status=revoked_status(event.name),
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
        # A duplicate only if the delivery is now on record: the same body
        # landing twice at once, and the other copy wrote it. Anything else -
        # two *different* purchases by a new buyer racing to create the same
        # user row, a constraint the schema should not have - was not
        # applied, and answering 200 told Tribute never to retry it: the
        # customer paid and got nothing (backend audit B-04). An error makes
        # Tribute redeliver, and the redelivery finds the user in place.
        if await _delivery_recorded(body_sha256):
            logger.info(f"Webhook raced its own duplicate: {body_sha256[:12]}")
            return {
                "status": "success",
                "message": "Webhook already processed (race condition)",
            }
        logger.error(f"Webhook {event.name} not applied, integrity error: {e}")
        return _error("could not apply the event, retry it", 503)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return _error("internal error", 500)


async def _cancel(
    session: AsyncSession, event: TributeEvent, user_id: int, when: datetime
) -> str:
    """A subscription's renewal switched off. Returns the note to record.

    The customer has paid up to `expires_at` and keeps access until then;
    this used to revoke at once (backend audit B-09). Refunds and
    chargebacks still do. Only the subscription the event names is touched:
    a cancellation that matches no row changes nothing, where it used to
    close every row the user had - a lifetime purchase included. A row with
    no end date is a lifetime purchase, and a cancellation cannot shorten it.
    """
    row = None
    if event.access_key:
        row = await SubscriptionRepository.get_by_user_and_subscription_id(
            session, user_id, event.access_key
        )
    if row is None:
        return "nothing to cancel: no subscription under that id"
    if row.expires_at is None:
        return "cancellation of a purchase without an end date: unchanged"
    row.status = CANCELED
    row.expires_at = event.stated_expires_at or row.expires_at
    row.last_event_at = when
    await session.flush()
    return f"canceled, access until {row.expires_at:%Y-%m-%d %H:%M} UTC"


async def _delivery_recorded(body_sha256: str) -> bool:
    """Whether a delivery with this body is on record as processed."""
    try:
        async with get_db() as session:
            found = await WebhookEventRepository.get_by_body_sha256(session, body_sha256)
            return found is not None
    except Exception as e:
        logger.warning(f"Could not look the delivery up: {e}")
        return False


async def user_has_access(telegram_user_id: int) -> bool:
    """Whether this user may see paid content.

    Access is an active, unexpired row in `subscriptions` (a lifetime
    purchase is one with no expiry; a cancelled subscription counts until
    the end of the period paid for), or an activated certificate, or
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
    """Every product synced from Tribute, cheapest first.

    That is the whole catalogue - the access, the gift, the referral
    discount - so nothing that offers a user something to buy may take the
    list as it is: `access_product` picks the one the paywall sells.
    """
    try:
        async with get_db() as session:
            products = await ProductRepository.get_all(session)
            return products
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        return []


def is_access_product(product: Product) -> bool:
    """Whether buying this product is buying access for oneself.

    The gift is a certificate to hand on, and the referral product is the
    discounted page only an invited user is sent to. Both sit in the synced
    catalogue next to the access itself, and the paywall used to offer
    whichever of the three was cheapest (backend audit B-10).
    """
    if settings.gift_product_id and str(product.id) == str(settings.gift_product_id).strip():
        return False
    others = {url for url in (settings.gift_payment_url, settings.referral_payment_url) if url}
    return not ({product.t_link, product.web_link} & others)


def access_product(products: Iterable[Product]) -> Product | None:
    """The product the paywall sells, out of the synced catalogue.

    `ACCESS_PRODUCT_ID` names it, and then nothing else is offered in its
    place: a configured product that has not been synced yet means the plain
    payment page, never a guess. Without the setting it is the cheapest
    access product with a payment link - the choice the paywall always
    made, minus the gift and the referral discount.
    """
    catalogue = list(products)
    if settings.access_product_id:
        wanted = str(settings.access_product_id).strip()
        return next((p for p in catalogue if str(p.id) == wanted), None)
    candidates = [p for p in catalogue if is_access_product(p)]
    linked = [p for p in candidates if p.t_link or p.web_link]
    if linked:
        return linked[0]
    return candidates[0] if candidates else None


async def purchase_url_for(referred: bool = False) -> str:
    """The payment page a paywall links to, the Mini App's and the bot's.

    A user who arrived on someone's referral link is sent to the discounted
    Tribute product instead. Tribute owns the price, so choosing the page is
    the whole of the discount; with no discounted page configured everyone
    gets the ordinary one and the referral is still recorded.
    """
    discounted = referrals.payment_url_for(referred)
    if discounted:
        return discounted
    product = access_product(await get_products_for_purchase())
    link = (product.t_link or product.web_link) if product else None
    return link or settings.tribute_payment_url


async def user_is_referred(telegram_user_id: int) -> bool:
    """Whether this user came in on someone's invite. False when unsure."""
    try:
        async with get_db() as session:
            return await UserRepository.is_referred(session, telegram_user_id)
    except Exception as e:
        logger.warning(f"Referral lookup failed: {e}")
        return False


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
    """Formatted price of the access product, or None when it is unknown.

    The price of the product the buy button leads to, never of whichever
    product is cheapest: that was the gift or the referral discount as soon
    as either was synced (backend audit B-10).
    """
    product = access_product(await get_products_for_purchase())
    if product is None or not product.amount:
        return None
    return format_price(product.amount, product.currency or "eur")


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

            # One conditional UPDATE decides who gets the code. Two people
            # redeeming it in the same instant both passed the `is_used`
            # check above; only one of them changes a row here.
            claimed = await CertificateRepository.claim(
                session, code, telegram_user_id
            )
            if claimed is None:
                logger.warning(
                    f"Certificate #{certificate.id} was claimed by someone else first"
                )
                return {
                    "status": "error",
                    "message": "Certificate already used",
                    "code": 409,
                }
            certificate = claimed

            await session.commit()

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
