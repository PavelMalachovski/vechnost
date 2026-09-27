"""Service layer for payment operations."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
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
from .models import Product, Subscription
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
    # The same event in other bytes: Tribute stamps every attempt with its
    # own `sent_at` (backend audit B-07).
    event_key = event.idempotency_key
    action = event.action
    now = datetime.utcnow()
    # When it happened, by Tribute's clock: what orders this event against
    # the ones already applied. Deliveries arrive late and out of order - a
    # retry of a purchase can land after its own refund - so the order they
    # arrive in decides nothing (backend audit B-08).
    happened_at = event.created_at or now

    try:
        async with get_db() as session:
            existing = await WebhookEventRepository.get_by_body_sha256(
                session, body_sha256
            )
            if existing is None and event_key:
                existing = await WebhookEventRepository.get_by_event_key(session, event_key)
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
            language = gift_language(user.language)

            if action == "grant" and is_gift_purchase(event.product_id):
                outcome = await _issue_gift(session, event)
            elif action == "grant":
                outcome = await _grant(session, event, user.id, happened_at)
            elif action == "cancel":
                outcome = await _cancel(session, event, user.id, happened_at)
            elif action == "revoke" and await _refunds_a_gift(session, event):
                outcome = await _revoke_gift(session, event, now)
            elif action == "revoke":
                outcome = await _revoke(session, event, user.id, happened_at)
            else:
                outcome = _Outcome(note="ignored: unknown event")
                logger.warning(
                    f"Webhook {event.name!r} is not an event this code knows; "
                    "acknowledged and left without effect"
                )
            if outcome.note:
                logger.info(f"{event.name} for {telegram_user_id}: {outcome.note}")

            payment_id: int | None = None
            if action != "ignore" and not outcome.stale:
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

            await WebhookEventRepository.create(
                session,
                name=event.name,
                sent_at=event.sent_at or event.created_at or now,
                body_sha256=body_sha256,
                event_key=event_key,
                status_code=200,
                processed_at=now,
                error=outcome.note,
            )

            result = {
                "status": "success",
                "message": (
                    "Stale event ignored" if outcome.stale
                    else "Webhook processed successfully"
                ),
                "action": "ignore" if outcome.stale else action,
                "note": outcome.note,
                "payment_id": payment_id,
                # Who, and what kind of grant: the endpoint tells a buyer
                # their own access is open - not for a present (a gift is not
                # that), not for a renewal (nothing new opened), and in words
                # that say "for good" only when it is.
                "telegram_user_id": telegram_user_id,
                "gift": action == "grant" and is_gift_purchase(event.product_id),
                "renewal": event.name.lower() == "renewed_subscription",
                "lifetime": event.expires_at is None,
            }

    except IntegrityError as e:
        # A duplicate only if the delivery is now on record: the same event
        # landing twice at once, and the other copy wrote it. Anything else -
        # two *different* purchases by a new buyer racing to create the same
        # user row, a constraint the schema should not have - was not
        # applied, and answering 200 told Tribute never to retry it: the
        # customer paid and got nothing (backend audit B-04). An error makes
        # Tribute redeliver, and the redelivery finds the user in place.
        if await _delivery_recorded(body_sha256, event_key):
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

    if outcome.gift_code:
        # Only now, with the certificate committed: sending it from inside
        # the transaction handed out codes for certificates a failed commit
        # then rolled back, and kept a database connection waiting on a
        # render and a Telegram round trip.
        try:
            await deliver_gift_certificate(telegram_user_id, outcome.gift_code, language)
        except Exception as e:
            # The certificate exists either way; support can find it by the
            # purchase and send the code by hand.
            logger.error(f"Failed to deliver gift certificate: {e}")
    return result


@dataclass
class _Outcome:
    """What one delivery did: the note it is recorded with, whether it was
    older than what it would have changed and so changed nothing, and a
    gift code minted by it, to send once the transaction has committed."""

    note: str | None = None
    stale: bool = False
    gift_code: str | None = None


async def _issue_gift(session: AsyncSession, event: TributeEvent) -> _Outcome:
    """A present: the buyer gets a certificate to hand on, not access of
    their own.

    One certificate per purchase. A purchase Tribute names by id finds the
    certificate it already paid for, however often and however late it is
    delivered; one without an id relies on the event key to be seen once.
    """
    purchase_id = event.purchase_id
    if purchase_id:
        issued = await CertificateRepository.get_by_purchase(session, purchase_id)
        if issued is not None and issued.revoked_at is not None:
            return _Outcome(note="gift purchase already refunded: no certificate issued")
        if issued is not None:
            return _Outcome(note=f"gift certificate #{issued.id} already issued for this purchase")
    code = await create_gift_certificate(session, purchase_id=purchase_id)
    return _Outcome(note="gift certificate issued", gift_code=code)


async def _refunds_a_gift(session: AsyncSession, event: TributeEvent) -> bool:
    """Whether a refund or chargeback is of a gift purchase: the gift
    product, or a purchase a certificate was issued for, whatever product
    the refund does or does not name."""
    if is_gift_purchase(event.product_id):
        return True
    if not event.purchase_id:
        return False
    return await CertificateRepository.get_by_purchase(session, event.purchase_id) is not None


async def _revoke_gift(session: AsyncSession, event: TributeEvent, now: datetime) -> _Outcome:
    """A gift purchase refunded or charged back: its certificate stops working.

    Never the buyer's own access. The refund used to be handed to the
    subscription path, which found no row under the gift product and closed
    every row the buyer had - their own purchase went, and the gift code
    stayed good for life (backend audit B-06). The certificate is found by
    the purchase id the refund carries and revoked, redeemed or not;
    `user_has_access` stops counting it. A refund that arrives before its
    purchase is recorded as an already revoked certificate for that
    purchase, so the purchase, when it comes, mints nothing. Without a
    purchase id there is no telling which certificate is meant: nothing
    changes, and the delivery is recorded for someone to look at.
    """
    purchase_id = event.purchase_id
    if not purchase_id:
        logger.warning(
            f"{event.name} of a gift purchase carries no purchase id: no "
            "certificate can be matched to it, and none was revoked"
        )
        return _Outcome(note="gift refund not applied: the purchase could not be identified")
    certificate = await CertificateRepository.get_by_purchase(
        session, purchase_id, for_update=True
    )
    if certificate is None:
        await create_gift_certificate(session, purchase_id=purchase_id)
        certificate = await CertificateRepository.get_by_purchase(session, purchase_id)
        if certificate is not None:
            certificate.revoked_at = now
            await session.flush()
        return _Outcome(note="gift refunded before its purchase arrived: no certificate will be issued")
    if certificate.revoked_at is not None:
        return _Outcome(note=f"gift certificate #{certificate.id} already revoked")
    certificate.revoked_at = now
    await session.flush()
    redeemed = ", which had been redeemed" if certificate.is_used else ""
    logger.warning(f"Gift certificate #{certificate.id}{redeemed} revoked by {event.name}")
    return _Outcome(note=f"gift certificate #{certificate.id}{redeemed} revoked")


def _stale(row: Subscription | None, happened_at: datetime) -> _Outcome | None:
    """The outcome for an event older than the last one applied to `row`.

    `last_event_at` holds the time of that event by Tribute's clock, so a
    purchase delivered after its own refund - a retry, a redelivery from
    the dashboard, a first attempt that failed - is older than the refund
    and changes nothing (backend audit B-08). It used to hold the time of
    processing, and whichever delivery arrived last won.
    """
    if row is None or row.last_event_at <= happened_at:
        return None
    return _Outcome(
        note=(
            f"stale event ignored: it happened at {happened_at:%Y-%m-%d %H:%M:%S}, "
            f"and an event of {row.last_event_at:%Y-%m-%d %H:%M:%S} already "
            "decided this access"
        ),
        stale=True,
    )


async def _grant(
    session: AsyncSession, event: TributeEvent, user_id: int, happened_at: datetime
) -> _Outcome:
    """A purchase or a renewal: the row it is filed under becomes active."""
    row = await SubscriptionRepository.get_by_user_and_subscription_id(
        session, user_id, event.access_key, for_update=True
    )
    stale = _stale(row, happened_at)
    if stale:
        return stale
    await SubscriptionRepository.upsert(
        session,
        user_id=user_id,
        subscription_id=event.access_key,
        period=event.period,
        status="active",
        expires_at=event.expires_at,
        last_event_at=happened_at,
    )
    logger.info(
        f"Access granted to user #{user_id} by {event.name}: "
        f"period={event.period}, expires_at={event.expires_at}"
    )
    return _Outcome()


async def _cancel(
    session: AsyncSession, event: TributeEvent, user_id: int, happened_at: datetime
) -> _Outcome:
    """A subscription's renewal switched off.

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
            session, user_id, event.access_key, for_update=True
        )
    if row is None:
        return _Outcome(note="nothing to cancel: no subscription under that id")
    stale = _stale(row, happened_at)
    if stale:
        return stale
    if row.expires_at is None:
        return _Outcome(note="cancellation of a purchase without an end date: unchanged")
    row.status = CANCELED
    row.expires_at = event.stated_expires_at or row.expires_at
    row.last_event_at = happened_at
    await session.flush()
    return _Outcome(note=f"canceled, access until {row.expires_at:%Y-%m-%d %H:%M} UTC")


async def _revoke(
    session: AsyncSession, event: TributeEvent, user_id: int, happened_at: datetime
) -> _Outcome:
    """A refund or a chargeback of the user's own access: it ends now.

    The row the event names is the one closed. When the user has no such
    row, every row that still grants access is closed instead - a refund
    with no effect is worse than one with too much - and the refund is
    remembered under the name it gave, so the purchase it undoes, should
    its delivery come later, is older than the refund and grants nothing.
    That fallback is an anomaly and is logged as one; a gift's refund never
    reaches it (see `_revoke_gift`).
    """
    status = revoked_status(event.name)
    if event.access_key:
        row = await SubscriptionRepository.get_by_user_and_subscription_id(
            session, user_id, event.access_key, for_update=True
        )
        if row is not None:
            stale = _stale(row, happened_at)
            if stale:
                return stale
            row.status = status
            row.last_event_at = happened_at
            await session.flush()
            return _Outcome(note=f"revoked 1 ({status})")

    revoked = await SubscriptionRepository.revoke_all_for_user(
        session, user_id, status=status, when=happened_at
    )
    logger.warning(
        f"Anomaly: {event.name} for user #{user_id} names no row they hold "
        f"(id {event.access_key or 'none'}); closed every row that granted "
        f"access instead: {revoked}"
    )
    if event.access_key:
        await SubscriptionRepository.upsert(
            session,
            user_id=user_id,
            subscription_id=event.access_key,
            period=event.period,
            status=status,
            expires_at=None,
            last_event_at=happened_at,
        )
    return _Outcome(note=f"revoked {revoked} ({status}): no row under the id it names")


async def _delivery_recorded(body_sha256: str, event_key: str | None = None) -> bool:
    """Whether this delivery is on record as processed: these bytes, or the
    same event in other bytes."""
    try:
        async with get_db() as session:
            if await WebhookEventRepository.get_by_body_sha256(session, body_sha256):
                return True
            if event_key:
                return await WebhookEventRepository.get_by_event_key(session, event_key) is not None
            return False
    except Exception as e:
        logger.warning(f"Could not look the delivery up: {e}")
        return False


async def user_has_access(telegram_user_id: int) -> bool:
    """Whether this user may see paid content.

    Access is an active, unexpired row in `subscriptions` (a lifetime
    purchase is one with no expiry; a cancelled subscription counts until
    the end of the period paid for), or an activated certificate that has
    not been revoked, or payments being switched off altogether. A row in `payments` is a
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

            # A certificate whose purchase was refunded stops counting,
            # redeemed or not (backend audit B-06).
            certificates = [
                certificate
                for certificate in await CertificateRepository.get_by_user(
                    session, telegram_user_id
                )
                if certificate.revoked_at is None
            ]
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

            # The gift it was issued for was refunded or charged back.
            if certificate.revoked_at is not None:
                logger.warning(
                    f"Certificate #{certificate.id} is revoked: its purchase was refunded"
                )
                return {
                    "status": "error",
                    "message": "Certificate revoked",
                    "code": 410,
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
                # Someone else claimed it first - or, rarer, its refund landed
                # in between; the claim refuses a revoked code either way.
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
