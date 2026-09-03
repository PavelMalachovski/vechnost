"""The Tribute webhook, end to end, in the shape Tribute actually sends.

Three things were wrong at once and each has a test that fails without
its fix: the signature was read from a header Tribute never sends and
compared against a key Tribute never had (F01); a rejected delivery was
recorded under the body's hash, so the correctly signed retry was told
"already processed" and the payment was lost (F02); and every event, a
cancellation included, wrote a `payments` row that counted as lifetime
access (F03). Nothing here mocks the verifier: the bodies are signed the
way Tribute signs them.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments import throttle
from vechnost_bot.payments.models import (
    Certificate,
    Payment,
    Subscription,
    User,
    WebhookEvent,
)
from vechnost_bot.payments.repositories import (
    PaymentRepository,
    UserRepository,
    WebhookEventRepository,
)
from vechnost_bot.payments.services import user_has_access
from vechnost_bot.payments.signature import verify_tribute_signature
from vechnost_bot.payments.tribute_event import TributeEvent, action_for
from vechnost_bot.payments.web import MAX_WEBHOOK_BODY, app

API_KEY = "tribute-api-key-for-tests"
BUYER = 424242


@pytest.fixture
def client(tmp_path):
    """Payments on, the API key configured, a fresh database."""
    db_path = tmp_path / "webhook.db"
    with (
        patch.object(settings, "database_url", f"sqlite:///{db_path}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "tribute_api_key", API_KEY),
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "gift_product_id", None),
    ):
        throttle.reset()
        yield TestClient(app)


def sign(body: bytes, key: str = API_KEY, encoding: str = "hex") -> str:
    digest = hmac.new(key.encode(), body, hashlib.sha256).digest()
    return digest.hex() if encoding == "hex" else base64.b64encode(digest).decode()


def event(name: str, telegram_user_id: int = BUYER, **payload) -> bytes:
    """A delivery in Tribute's shape: name, timestamps, and the purchase."""
    body = {
        "name": name,
        "created_at": "2026-09-01T10:00:00Z",
        "sent_at": "2026-09-01T10:00:01Z",
        "payload": {
            "telegram_user_id": telegram_user_id,
            "user_id": 100,
            "amount": 990,
            "currency": "eur",
            **payload,
        },
    }
    return json.dumps(body, ensure_ascii=False).encode()


def deliver(client, body: bytes, signature: str | None = None, header: str = "trbt-signature"):
    return client.post(
        "/webhooks/tribute",
        content=body,
        headers={"Content-Type": "application/json", header: signature or sign(body)},
    )


def access(telegram_user_id: int = BUYER) -> bool:
    return asyncio.run(user_has_access(telegram_user_id))


def rows(model):
    async def go():
        async with database.get_db() as session:
            return list((await session.execute(select(model))).scalars().all())

    return asyncio.run(go())


# ---------------------------------------------------------------------------
# F01: the signature Tribute actually sends
# ---------------------------------------------------------------------------

def test_a_real_delivery_grants_access(client):
    """The purchase Tribute reports, signed with the API key in trbt-signature."""
    response = deliver(client, event("new_digital_product", product_id=555))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert access() is True

    [subscription] = rows(Subscription)
    assert subscription.status == "active"
    assert subscription.expires_at is None, "a product is forever"
    assert subscription.period == "lifetime"


def test_the_api_key_is_the_signing_key():
    body = b'{"name":"new_digital_product","payload":{"telegram_user_id":1}}'
    with (
        patch.object(settings, "tribute_api_key", "the-key"),
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "enable_payment", True),
    ):
        assert verify_tribute_signature({"trbt-signature": sign(body, "the-key")}, body)
        assert not verify_tribute_signature({"trbt-signature": sign(body, "other")}, body)


def test_webhook_secret_is_an_extra_key_not_a_replacement():
    """A relay in front of the endpoint may sign with its own secret; the
    API key must keep working next to it, or Tribute's own deliveries fail."""
    body = b'{"name":"new_digital_product"}'
    with (
        patch.object(settings, "tribute_api_key", "the-key"),
        patch.object(settings, "webhook_secret", "relay-secret"),
        patch.object(settings, "enable_payment", True),
    ):
        assert verify_tribute_signature({"trbt-signature": sign(body, "the-key")}, body)
        assert verify_tribute_signature({"trbt-signature": sign(body, "relay-secret")}, body)
        assert not verify_tribute_signature({"trbt-signature": sign(body, "guess")}, body)


def test_a_base64_signature_is_accepted(client):
    body = event("new_digital_product", product_id=555)
    response = deliver(client, body, signature=sign(body, encoding="base64"))
    assert response.status_code == 200
    assert access() is True


def test_a_delivery_with_the_wrong_key_is_refused(client):
    response = deliver(client, event("new_digital_product"), signature=sign(b"other body"))
    assert response.status_code == 401
    assert access() is False


def test_a_signature_from_a_key_that_is_not_ours_is_refused(client):
    body = event("new_digital_product")
    response = deliver(client, body, signature=sign(body, key="not-our-key"))
    assert response.status_code == 401
    assert access() is False


# ---------------------------------------------------------------------------
# F02: a rejected delivery must not poison its own retry
# ---------------------------------------------------------------------------

def test_a_rejected_delivery_leaves_no_trace(client):
    """Nothing is written before the signature is checked: no user, no
    payment, no webhook record. A stranger cannot fill the tables, and a
    delivery refused today is not remembered tomorrow."""
    body = event("new_digital_product", product_id=555)
    assert deliver(client, body, signature="0" * 64).status_code == 401
    assert rows(WebhookEvent) == []
    assert rows(Payment) == []
    assert rows(User) == []


def test_the_retry_of_a_rejected_delivery_is_processed(client):
    """The exact bytes Tribute retries, first with a signature we did not
    accept (a mis-set key), then correctly. The second must count."""
    body = event("new_digital_product", product_id=555)
    assert deliver(client, body, signature=sign(body, key="stale-key")).status_code == 401
    assert access() is False

    retry = deliver(client, body)
    assert retry.status_code == 200
    assert retry.json()["message"] == "Webhook processed successfully"
    assert access() is True


def test_the_same_delivery_twice_is_processed_once(client):
    body = event("new_digital_product", product_id=555)
    assert deliver(client, body).status_code == 200
    again = deliver(client, body)
    assert again.status_code == 200
    assert "idempotent" in again.json()["message"]
    assert len(rows(Payment)) == 1
    assert len(rows(Subscription)) == 1


# ---------------------------------------------------------------------------
# F03: what an event does is a table, and a payment row is not access
# ---------------------------------------------------------------------------

def test_a_cancellation_revokes_access(client):
    assert deliver(client, event("new_subscription", subscription_id=77,
                                 expires_at="2099-01-01T00:00:00Z")).status_code == 200
    assert access() is True

    response = deliver(client, event("cancelled_subscription", subscription_id=77))
    assert response.status_code == 200
    assert access() is False
    [subscription] = rows(Subscription)
    assert subscription.status == "canceled"


def test_a_refund_of_a_product_revokes_access(client):
    assert deliver(client, event("new_digital_product", product_id=555)).status_code == 200
    assert access() is True

    assert deliver(client, event("digital_product_refunded", product_id=555)).status_code == 200
    assert access() is False
    [subscription] = rows(Subscription)
    assert subscription.status == "refunded"


def test_a_cancellation_never_grants(client):
    """The bug this replaces: a cancellation wrote a payment row with no
    expiry, and a payment row with no expiry was lifetime access."""
    response = deliver(client, event("cancelled_subscription", subscription_id=77))
    assert response.status_code == 200
    assert access() is False
    assert rows(Subscription) == []


def test_an_unknown_event_is_acknowledged_and_changes_nothing(client):
    response = deliver(client, event("new_donation", product_id=1))
    assert response.status_code == 200, "Tribute must not retry an event we do not handle"
    assert response.json()["action"] == "ignore"
    assert access() is False
    assert rows(Payment) == [], "not a purchase, so not in the journal either"
    [record] = rows(WebhookEvent)
    assert record.status_code == 200
    assert "ignored" in (record.error or "")


def test_a_subscription_without_an_expiry_is_not_forever(client):
    """A monthly plan must not become lifetime because a field was missing."""
    assert deliver(client, event("new_subscription", subscription_id=5)).status_code == 200
    [subscription] = rows(Subscription)
    assert subscription.expires_at is not None
    assert subscription.expires_at < datetime.utcnow() + timedelta(days=31)


def test_a_gift_purchase_issues_a_certificate_not_access(client):
    with (
        patch.object(settings, "gift_product_id", "777"),
        patch("vechnost_bot.payments.services.deliver_gift_certificate", new=AsyncMock()),
    ):
        response = deliver(client, event("new_digital_product", product_id=777))
    assert response.status_code == 200
    assert access() is False, "the buyer hands the code on; it is not theirs"
    [certificate] = rows(Certificate)
    assert certificate.is_used is False


def test_the_event_table():
    assert action_for("new_digital_product") == "grant"
    assert action_for("new_subscription") == "grant"
    assert action_for("renewed_subscription") == "grant"
    assert action_for("cancelled_subscription") == "revoke"
    assert action_for("subscription_refunded") == "revoke"
    assert action_for("chargeback") == "revoke"
    assert action_for("new_donation") == "ignore"
    assert action_for("subscription.created") == "ignore", "not a Tribute name"


def test_the_payload_is_read_from_where_tribute_puts_it():
    parsed = TributeEvent.parse(json.loads(event(
        "new_subscription", subscription_id=9, period="monthly",
        expires_at="2030-05-06T07:08:09Z",
    )))
    assert parsed.telegram_user_id == BUYER
    assert parsed.subscription_id == 9
    assert parsed.access_key == 9
    assert parsed.period == "monthly"
    assert parsed.expires_at == datetime(2030, 5, 6, 7, 8, 9)
    assert parsed.expires_at.tzinfo is None, "the columns are naive UTC"
    assert parsed.amount == 990
    assert parsed.currency == "eur"


def test_a_non_numeric_buyer_is_a_400_not_a_500(client):
    body = event("new_digital_product", telegram_user_id="not-a-number")
    assert deliver(client, body).status_code == 400
    assert rows(WebhookEvent) == []


# ---------------------------------------------------------------------------
# The endpoint itself
# ---------------------------------------------------------------------------

def test_an_oversized_body_is_refused_before_it_is_read(client):
    body = b'{"name":"new_digital_product","pad":"' + b"x" * MAX_WEBHOOK_BODY + b'"}'
    response = deliver(client, body)
    assert response.status_code == 413


def test_deliveries_are_throttled(client):
    limit, _ = throttle.LIMITS["webhook"]
    body = event("new_digital_product")
    statuses = [
        deliver(client, body, signature="0" * 64).status_code for _ in range(limit + 2)
    ]
    assert statuses[0] == 401
    assert statuses[-1] == 429


# ---------------------------------------------------------------------------
# What a deploy does to the data already there
# ---------------------------------------------------------------------------

@pytest.fixture
def memory_db():
    with (
        patch.object(settings, "database_url", "sqlite+aiosqlite:///:memory:"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
        patch.object(settings, "enable_payment", True),
    ):
        yield


async def test_a_payment_row_alone_is_not_access_and_is_backfilled_once(memory_db):
    """Access no longer derives from `payments`; whoever had it that way
    keeps it through the backfill that runs at startup."""
    await database.create_tables()
    async with database.get_db() as session:
        user = await UserRepository.create_or_update(session, telegram_user_id=1001)
        await PaymentRepository.create(
            session, provider="tribute", event_name="new_digital_product",
            user_id=user.id, telegram_user_id=1001, amount=990, currency="eur",
            raw_body={}, signature="", body_sha256="abc", expires_at=None,
        )
    assert await user_has_access(1001) is False

    await database.create_tables()   # the next deploy
    assert await user_has_access(1001) is True

    await database.create_tables()   # and the one after: nothing doubles
    async with database.get_db() as session:
        found = list((await session.execute(select(Subscription))).scalars().all())
    assert len(found) == 1
    assert found[0].period == "lifetime" and found[0].expires_at is None


async def test_rejected_delivery_records_are_released_at_startup(memory_db):
    """The rows that stood between a lost payment and its retry."""
    await database.create_tables()
    async with database.get_db() as session:
        await WebhookEventRepository.create(
            session, name="new_digital_product", sent_at=datetime.utcnow(),
            body_sha256="stuck", status_code=401, error="Invalid webhook signature",
        )
        await WebhookEventRepository.create(
            session, name="new_digital_product", sent_at=datetime.utcnow(),
            body_sha256="fine", status_code=200,
        )
    await database.create_tables()
    async with database.get_db() as session:
        left = list((await session.execute(select(WebhookEvent))).scalars().all())
    assert [row.body_sha256 for row in left] == ["fine"]
