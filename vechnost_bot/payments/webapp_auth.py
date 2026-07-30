"""Validation of Telegram Mini App initData.

Implements the official verification scheme:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

DEFAULT_MAX_AGE_SECONDS = 86_400  # 24 hours


class InitDataError(Exception):
    """Raised when initData is missing, malformed, forged or stale."""


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """
    Verify the signature and freshness of a Mini App initData string.

    Args:
        init_data: Raw ``window.Telegram.WebApp.initData`` query string.
        bot_token: The bot token the Mini App belongs to.
        max_age_seconds: Reject payloads whose auth_date is older than this.

    Returns:
        Parsed initData fields; ``user`` is decoded from JSON and
        ``auth_date`` is an int.

    Raises:
        InitDataError: If the payload is empty, unsigned, forged,
            stale or missing the user field.
    """
    if not init_data:
        raise InitDataError("initData is empty")

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError as e:
        raise InitDataError(f"initData is not a valid query string: {e}") from e

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("initData has no hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("initData signature mismatch")

    try:
        auth_date = int(pairs.get("auth_date", ""))
    except ValueError as e:
        raise InitDataError("initData has no valid auth_date") from e

    if time.time() - auth_date > max_age_seconds:
        raise InitDataError("initData is stale")

    if "user" not in pairs:
        raise InitDataError("initData has no user")

    try:
        user = json.loads(pairs["user"])
    except (TypeError, json.JSONDecodeError) as e:
        raise InitDataError("initData user is not valid JSON") from e

    if not isinstance(user, dict) or "id" not in user:
        raise InitDataError("initData user has no id")

    parsed: dict[str, Any] = dict(pairs)
    parsed["auth_date"] = auth_date
    parsed["user"] = user
    return parsed
