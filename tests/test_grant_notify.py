"""The buyer hears «всё открыто» in the chat - once, for their own purchase.

A purchase happens on Tribute's page, and nothing there says where to go
next. The web process tells the buyer the moment the webhook confirms it:
access is open for good, here is the button into the app, and the partner
does not pay again. Never for a gift (the buyer holds a certificate to hand
on), a duplicate delivery, a refund or cancellation, or an event nobody
knows - and never before Tribute has its answer.

Sync tests driving coroutines with `asyncio.run()`, as test_compat_notify.py
does. The autouse fixture in conftest.py already keeps `_bot` from dialling
Telegram; the tests about the message patch it again with a mock.
"""

import asyncio
import hashlib
import hmac
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient
from telegram.error import Forbidden

import vechnost_bot.payments.database as database
import vechnost_bot.payments.web as web
from vechnost_bot.config import settings
from vechnost_bot.i18n import Language, get_text
from vechnost_bot.payments import grant_notify, throttle
from vechnost_bot.payments.grant_notify import notify_access_granted

API_KEY = "tribute-api-key-for-grant-tests"
BUYER = 515151


# ---------------------------------------------------------------------------
# The message
# ---------------------------------------------------------------------------


def _send(user_id: int = BUYER, bot=None, language: str | None = "ru", lifetime: bool = True):
    if bot is None:
        bot = MagicMock()
        bot.send_message = AsyncMock()
    user = None if language is None else MagicMock(language=language)
    with (
        patch("vechnost_bot.payments.repositories.UserRepository") as repo,
        patch("vechnost_bot.payments.database.get_db"),
        patch.object(grant_notify, "_bot", return_value=bot),
    ):
        repo.get_by_telegram_id = AsyncMock(return_value=user)
        asyncio.run(notify_access_granted(user_id, lifetime))
    return bot


def test_the_buyer_is_told_everything_is_open_for_good():
    with patch.object(settings, "webapp_url", "https://example.com/app"):
        bot = _send()
    bot.send_message.assert_awaited_once()
    sent = bot.send_message.await_args.kwargs
    assert sent["chat_id"] == BUYER
    text = sent["text"]
    assert text == get_text("grant.message", Language.RUSSIAN)
    assert "навсегда" in text
    assert "партнёру платить не нужно" in text, "the question every couple asks next"


def test_a_subscription_is_not_called_forever():
    bot = _send(lifetime=False)
    text = bot.send_message.await_args.kwargs["text"]
    assert text == get_text("grant.message_subscription", Language.RUSSIAN)
    assert "навсегда" not in text
    assert "партнёру платить не нужно" in text


def test_the_button_opens_the_mini_app_not_the_in_app_browser():
    """`url=` lands in Telegram's browser, where initData is empty and the
    app cannot tell the buyer from a stranger: the paywall they just paid."""
    with patch.object(settings, "webapp_url", "https://example.com/app"):
        bot = _send()
    button = bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.web_app is not None and button.web_app.url == "https://example.com/app"
    assert button.url is None
    assert button.text == get_text("grant.open_button", Language.RUSSIAN)


def test_without_a_webapp_url_the_message_is_plain_text():
    with patch.object(settings, "webapp_url", None):
        bot = _send()
    assert bot.send_message.await_args.kwargs["reply_markup"] is None


def test_a_buyer_who_never_opened_the_chat_does_not_break_anything():
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=Forbidden("bot can't initiate conversation"))
    _send(bot=bot)  # must not raise
    bot.send_message.assert_awaited_once()


def test_a_stored_retired_language_still_reads_russian():
    bot = _send(language="en")
    assert bot.send_message.await_args.kwargs["text"] == get_text("grant.message", Language.RUSSIAN)
    bot = _send(language=None)
    assert bot.send_message.await_args.kwargs["text"] == get_text("grant.message", Language.RUSSIAN)


def test_no_bot_configured_is_silent():
    with patch.object(grant_notify, "_bot", return_value=None):
        asyncio.run(notify_access_granted(BUYER))  # must not raise


def test_a_dead_network_is_swallowed():
    bot = MagicMock()
    bot.__aenter__ = AsyncMock(side_effect=OSError("network is unreachable"))
    bot.__aexit__ = AsyncMock(return_value=False)
    _send(bot=bot)  # must not raise


# ---------------------------------------------------------------------------
# When the webhook sends it
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    """Payments on, the API key configured, a fresh database, a mock push."""
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'grant.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "tribute_api_key", API_KEY),
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "gift_product_id", None),
    ):
        throttle.reset()
        yield TestClient(app_under_test())


def app_under_test():
    return web.app


@pytest.fixture
def push():
    with patch.object(web, "notify_access_granted", new_callable=AsyncMock) as mock:
        yield mock


def event(name: str, telegram_user_id: int = BUYER, **payload) -> bytes:
    return json.dumps(
        {
            "name": name,
            "created_at": "2026-09-01T10:00:00Z",
            "sent_at": "2026-09-01T10:00:01Z",
            "payload": {
                "telegram_user_id": telegram_user_id,
                "amount": 990,
                "currency": "eur",
                **payload,
            },
        }
    ).encode()


def deliver(client, body: bytes, key: str = API_KEY):
    signature = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/tribute",
        content=body,
        headers={"Content-Type": "application/json", "trbt-signature": signature},
    )


def test_a_purchase_tells_the_buyer_once(client, push):
    body = event("new_digital_product", product_id=555)
    response = deliver(client, body)
    assert response.status_code == 200 and response.json()["action"] == "grant"
    push.assert_awaited_once_with(BUYER, True)

    # Tribute redelivers for a day: the same bytes again are a duplicate,
    # and a duplicate tells nobody anything twice.
    again = deliver(client, body)
    assert again.status_code == 200 and "idempotent" in again.json()["message"]
    assert push.await_count == 1


def test_a_subscription_tells_the_buyer_too_but_not_that_it_is_for_good(client, push):
    deliver(client, event("new_subscription", subscription_id=9, expires_at="2099-01-01T00:00:00Z"))
    push.assert_awaited_once_with(BUYER, False)


def test_a_renewal_tells_the_buyer_nothing_new(client, push):
    """Every month a subscription renews; «всё открыто» each time would be
    noise about something that opened long ago."""
    deliver(client, event("new_subscription", subscription_id=9, expires_at="2099-01-01T00:00:00Z"))
    push.reset_mock()
    response = deliver(
        client,
        json.dumps(
            {
                "name": "renewed_subscription",
                "created_at": "2026-10-01T10:00:00Z",
                "sent_at": "2026-10-01T10:00:01Z",
                "payload": {
                    "telegram_user_id": BUYER,
                    "subscription_id": 9,
                    "expires_at": "2099-02-01T00:00:00Z",
                },
            }
        ).encode(),
    )
    assert response.status_code == 200 and response.json()["action"] == "grant"
    push.assert_not_awaited()


def test_a_gift_tells_the_buyer_nothing_of_the_kind(client, push):
    """The buyer of a present gets a certificate to hand on, not access:
    «всё открыто» would be a lie to them."""
    with (
        patch.object(settings, "gift_product_id", "777"),
        patch("vechnost_bot.payments.services.deliver_gift_certificate", new=AsyncMock()),
    ):
        response = deliver(client, event("new_digital_product", product_id=777))
    assert response.status_code == 200 and response.json()["action"] == "grant"
    push.assert_not_awaited()


@pytest.mark.parametrize("name", ["refund", "cancelled_subscription", "new_donation"])
def test_a_refund_a_cancellation_or_an_unknown_event_tells_nobody(client, push, name):
    deliver(client, event("new_digital_product", product_id=555))
    push.reset_mock()
    response = deliver(client, event(name, product_id=555, subscription_id=9))
    assert response.status_code == 200
    push.assert_not_awaited()


def test_a_forged_delivery_tells_nobody(client, push):
    response = deliver(client, event("new_digital_product", product_id=555), key="not-ours")
    assert response.status_code == 401
    push.assert_not_awaited()


def test_an_unsigned_delivery_before_launch_tells_nobody(client, push):
    """Payments off and no key: the delivery is acknowledged and not applied,
    so there is nothing to announce either."""
    body = event("new_digital_product", product_id=555)
    with (
        patch.object(settings, "enable_payment", False),
        patch.object(settings, "tribute_api_key", None),
    ):
        response = client.post(
            "/webhooks/tribute", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 200 and response.json()["action"] == "ignore"
    push.assert_not_awaited()


def test_tributes_connectivity_ping_tells_nobody(client, push):
    response = deliver(client, json.dumps({"test": True}).encode())
    assert response.status_code == 200
    push.assert_not_awaited()


def test_the_answer_goes_to_tribute_before_the_message_goes_to_telegram(client):
    """The message is a getMe and a sendMessage with Telegram's timeouts; the
    webhook's answer must not wait on them. Driven at the ASGI level, because
    TestClient returns only once the background work is done too, and so
    cannot show which went out first. The push here cannot finish until the
    answer has been sent: sent inline, it would never finish at all."""
    body = event("new_digital_product", product_id=555)
    signature = hmac.new(API_KEY.encode(), body, hashlib.sha256).hexdigest()
    order: list[str] = []

    async def run() -> None:
        answered = asyncio.Event()

        async def slow_push(user_id: int, lifetime: bool = True) -> None:
            order.append("push started")
            await asyncio.wait_for(answered.wait(), timeout=5)
            order.append("push finished")

        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.sleep(3600)

        async def send(message):
            if message["type"] == "http.response.start":
                order.append(f"answer {message['status']}")
            if message["type"] == "http.response.body" and not message.get("more_body"):
                order.append("answer sent")
                answered.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/webhooks/tribute",
            "raw_path": b"/webhooks/tribute",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"trbt-signature", signature.encode()),
            ],
            "client": ("127.0.0.1", 40001),
            "server": ("testserver", 80),
        }
        with patch.object(web, "notify_access_granted", slow_push):
            await web.app(scope, receive, send)
            await database.close_db()

    asyncio.run(run())
    assert order[0] == "answer 200"
    assert "push finished" in order, "the message was still sent"
    assert order.index("answer sent") < order.index("push finished")
