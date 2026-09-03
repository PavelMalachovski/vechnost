"""Webhook signature verification for Tribute.

Tribute signs every delivery with HMAC-SHA256 over the raw request body,
keyed with the account's **API key**, and sends the digest in the
`trbt-signature` header (wiki.tribute.tg, API documentation, Webhooks).
There is no separate webhook secret on their side.

This module used to look for `X-Tribute-Signature`, a header Tribute never
sends, and compare against `WEBHOOK_SECRET`, a value Tribute never had. With
payments on, that refused every real delivery as unsigned, and because the
rejection was recorded under the body's hash, Tribute's retries were then
answered "already processed". Nobody who paid was ever let in by this code.

`TRIBUTE_API_KEY` is therefore the signing key. `WEBHOOK_SECRET` stays as an
override for a deployment that fronts the endpoint with its own signer (a
relay, a local test harness) and is accepted alongside the API key, never
instead of it. The old header names are still read so a hand-made test
delivery keeps working.
"""

import base64
import hashlib
import hmac
import logging
from collections.abc import Mapping

from ..config import settings

logger = logging.getLogger(__name__)

# Most likely first. Tribute's own header, then the two this code used to
# expect, which the test scripts still send.
SIGNATURE_HEADERS = ("trbt-signature", "x-tribute-signature", "x-signature")


def compute_body_sha256(body: bytes) -> str:
    """Hex SHA-256 of a request body, the idempotency key for a delivery."""
    return hashlib.sha256(body).hexdigest()


def signing_keys() -> list[str]:
    """Every key a delivery may be signed with, most likely first."""
    keys: list[str] = []
    for key in (settings.tribute_api_key, settings.webhook_secret):
        if key and key not in keys:
            keys.append(key)
    return keys


def signature_header(headers: Mapping[str, str]) -> str | None:
    """The signature a delivery carries, whichever header name it used."""
    lowered = {str(name).lower(): value for name, value in headers.items()}
    for name in SIGNATURE_HEADERS:
        value = lowered.get(name)
        if value:
            return str(value).strip()
    return None


def _encodings(key: str, body: bytes) -> tuple[bytes, bytes]:
    """The digest as hex and as base64: Tribute documents hex, a relay may not."""
    digest = hmac.new(key.encode("utf-8"), body, hashlib.sha256).digest()
    return digest.hex().encode("ascii"), base64.b64encode(digest)


def verify_tribute_signature(
    headers: Mapping[str, str],
    body: bytes,
    secret: str | None = None,
) -> bool:
    """Whether `body` was signed by a key this deployment trusts.

    Fails closed whenever the signature guards something: with payments on
    and no key configured, every delivery is refused, because accepting an
    unverifiable one would let anyone POST their own telegram_user_id and
    become a paying customer. With payments off there is no paywall to
    bypass and the check is skipped.
    """
    keys = [secret] if secret else signing_keys()
    if not keys:
        if settings.enable_payment:
            logger.error(
                "Neither TRIBUTE_API_KEY nor WEBHOOK_SECRET is configured while "
                "ENABLE_PAYMENT is on: rejecting the webhook rather than "
                "granting access on an unverifiable payload"
            )
            return False
        logger.warning("No webhook signing key configured, skipping verification")
        return True

    received = signature_header(headers)
    if not received:
        logger.warning("Webhook arrived without a signature header")
        return False
    if received.lower().startswith("sha256="):
        received = received.split("=", 1)[1]
    received_bytes = received.encode("utf-8", errors="replace")

    for key in keys:
        for candidate in _encodings(key, body):
            if hmac.compare_digest(candidate, received_bytes):
                return True

    logger.warning("Invalid webhook signature")
    return False
