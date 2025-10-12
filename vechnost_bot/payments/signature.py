"""Webhook signature verification for Tribute."""

import hmac
import hashlib
import logging
from typing import Mapping, Optional

from ..config import settings

logger = logging.getLogger(__name__)


def compute_body_sha256(body: bytes) -> str:
    """
    Compute SHA-256 hash of request body.

    Args:
        body: Raw request body bytes

    Returns:
        Hexadecimal SHA-256 hash
    """
    return hashlib.sha256(body).hexdigest()


def verify_tribute_signature(
    headers: Mapping[str, str],
    body: bytes,
    secret: Optional[str] = None,
) -> bool:
    """
    Verify Tribute webhook signature.

    This implementation uses HMAC-SHA256. Adjust the algorithm
    and header name based on actual Tribute documentation.

    Args:
        headers: Request headers
        body: Raw request body bytes
        secret: Webhook secret (defaults to settings.webhook_secret)

    Returns:
        True if signature is valid, False otherwise
    """
    if secret is None:
        secret = settings.webhook_secret

    if not secret:
        logger.warning("Webhook secret not configured, skipping signature verification")
        return True  # Skip verification if no secret configured

    # Get signature from headers
    # Adjust header name based on Tribute documentation
    # Common variations:
    # - X-Tribute-Signature
    # - X-Signature
    # - X-Hub-Signature-256
    signature_header = (
        headers.get("X-Tribute-Signature")
        or headers.get("x-tribute-signature")
        or headers.get("X-Signature")
        or headers.get("x-signature")
    )

    if not signature_header:
        logger.warning("No signature header found in request")
        return False

    try:
        # Compute expected signature using HMAC-SHA256
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        # Compare signatures (constant-time comparison)
        # Some services prefix with "sha256=" - handle both cases
        if signature_header.startswith("sha256="):
            signature_value = signature_header.split("=", 1)[1]
        else:
            signature_value = signature_header

        is_valid = hmac.compare_digest(expected_signature, signature_value)

        if not is_valid:
            logger.warning("Invalid webhook signature")
        else:
            logger.info("Webhook signature verified successfully")

        return is_valid

    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        return False


def verify_tribute_signature_alternative(
    headers: Mapping[str, str],
    body: bytes,
    secret: Optional[str] = None,
) -> bool:
    """
    Alternative signature verification method.

    Some services use different algorithms. This can be switched
    based on Tribute's actual implementation.

    Args:
        headers: Request headers
        body: Raw request body bytes
        secret: Webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    # Implement alternative verification if needed
    # For example, using SHA-1, different encoding, etc.
    return verify_tribute_signature(headers, body, secret)

