"""Tests for Telegram Mini App initData validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from vechnost_bot.payments.webapp_auth import (
    InitDataError,
    validate_init_data,
)

BOT_TOKEN = "1234567890:TEST_TOKEN_FOR_UNIT_TESTS"


def make_init_data(
    bot_token: str = BOT_TOKEN,
    user: dict | None = None,
    auth_date: int | None = None,
    tamper: bool = False,
    drop_hash: bool = False,
) -> str:
    """Build a signed initData query string the way Telegram does."""
    if user is None:
        user = {"id": 42, "first_name": "Test", "username": "tester"}
    if auth_date is None:
        auth_date = int(time.time())

    pairs = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if tamper:
        pairs["user"] = json.dumps({**user, "id": 999}, separators=(",", ":"))
    if not drop_hash:
        pairs["hash"] = signature
    return urlencode(pairs)


def test_valid_init_data_returns_user():
    init_data = make_init_data()
    parsed = validate_init_data(init_data, BOT_TOKEN)
    assert parsed["user"]["id"] == 42
    assert parsed["user"]["username"] == "tester"


def test_tampered_payload_rejected():
    init_data = make_init_data(tamper=True)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    init_data = make_init_data(bot_token="1234567890:ANOTHER_TOKEN")
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_missing_hash_rejected():
    init_data = make_init_data(drop_hash=True)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_empty_init_data_rejected():
    with pytest.raises(InitDataError):
        validate_init_data("", BOT_TOKEN)


def test_stale_auth_date_rejected():
    init_data = make_init_data(auth_date=int(time.time()) - 100_000)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN, max_age_seconds=86_400)


def test_fresh_auth_date_accepted_within_max_age():
    init_data = make_init_data(auth_date=int(time.time()) - 600)
    parsed = validate_init_data(init_data, BOT_TOKEN, max_age_seconds=86_400)
    assert parsed["auth_date"]


def test_missing_user_field_rejected():
    # Sign a payload that has no user entry at all.
    auth_date = str(int(time.time()))
    pairs = {"auth_date": auth_date, "query_id": "AAA"}
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InitDataError):
        validate_init_data(urlencode(pairs), BOT_TOKEN)
