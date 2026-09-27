"""What a Tribute event means, in whatever order and however often it arrives.

tests/test_webhook_contract.py holds the shape of a delivery and its
signature. This file holds its meaning, finding by finding of the September
2026 backend audit:

* B-09 - a cancellation switches the renewal off; the period already paid
  for runs to its end. Refunds and chargebacks still revoke at once.
* B-08 - events are applied in the order they happened, not the order
  they arrived: one older than the last event applied to that access is
  acknowledged, recorded, and changes nothing.

Every delivery here is signed the way Tribute signs it, and access is read
back through `user_has_access`, the one function that decides it.
"""

import hashlib
import hmac
import json
import os
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.models import Payment, Subscription, WebhookEvent
from vechnost_bot.payments.services import user_has_access
from vechnost_bot.payments.tribute_event import action_for
from vechnost_bot.payments.web import app

API_KEY = "tribute-api-key-for-tests"
BUYER = 515151
PRODUCT = 555  # the lifetime access
SUBSCRIPTION = 77


def iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


LATER = iso(datetime.utcnow() + timedelta(days=20))  # a period still running


class Tribute:
    """The sending end: signs and posts deliveries, reads access back."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def body(
        self,
        name: str,
        *,
        created_at: str = "2026-09-01T10:00:00.000000Z",
        sent_at: str | None = None,
        telegram_user_id: int = BUYER,
        **payload: Any,
    ) -> bytes:
        return json.dumps({
            "name": name,
            "created_at": created_at,
            "sent_at": sent_at or created_at,
            "payload": {
                "telegram_user_id": telegram_user_id,
                "amount": 990,
                "currency": "eur",
                **payload,
            },
        }).encode()

    def post(self, body: bytes) -> dict[str, Any]:
        signature = hmac.new(API_KEY.encode(), body, hashlib.sha256).hexdigest()
        response = self.client.post(
            "/webhooks/tribute", content=body,
            headers={"Content-Type": "application/json", "trbt-signature": signature},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def send(self, name: str, **kwargs: Any) -> dict[str, Any]:
        return self.post(self.body(name, **kwargs))

    def access(self, telegram_user_id: int = BUYER) -> bool:
        return self.client.portal.call(user_has_access, telegram_user_id)

    def subscriptions(self) -> dict[int, Subscription]:
        async def read() -> dict[int, Subscription]:
            async with database.get_db() as session:
                found = (await session.execute(select(Subscription))).scalars().all()
                return {row.subscription_id: row for row in found}

        return self.client.portal.call(read)


@pytest.fixture
def tribute(tmp_path) -> Iterator[Tribute]:
    """Payments on, the API key configured, a fresh database, one event loop."""
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'tribute.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "tribute_api_key", API_KEY),
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "gift_product_id", None),
        TestClient(app) as client,
    ):
        yield Tribute(client)


# ---------------------------------------------------------------------------
# B-09: a cancellation ends the renewal, not the period paid for
# ---------------------------------------------------------------------------

def test_the_event_table_tells_a_cancellation_from_money_going_back():
    assert action_for("cancelled_subscription") == "cancel"
    assert action_for("canceled_subscription") == "cancel"
    assert action_for("digital_product_refunded") == "revoke"
    assert action_for("refund") == "revoke"
    assert action_for("chargeback") == "revoke"
    assert action_for("cancelled_donation") == "cancel", "a cancellation, never a revocation"


def test_a_cancelled_subscription_is_access_until_the_period_ends(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    answer = tribute.send("cancelled_subscription", created_at="2026-09-02T10:00:00.000000Z",
                          subscription_id=SUBSCRIPTION, expires_at=LATER)
    assert answer["action"] == "cancel"
    assert tribute.access() is True, "paid for twenty more days"
    row = tribute.subscriptions()[SUBSCRIPTION]
    assert row.status == "canceled"
    assert row.expires_at is not None and row.expires_at > datetime.utcnow()


def test_a_cancellation_whose_period_is_over_ends_access(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    yesterday = iso(datetime.utcnow() - timedelta(days=1))
    tribute.send("cancelled_subscription", created_at="2026-09-02T10:00:00.000000Z",
                 subscription_id=SUBSCRIPTION, expires_at=yesterday)
    assert tribute.access() is False, "Tribute says the paid period ended yesterday"


def test_a_cancellation_does_not_touch_a_lifetime_purchase(tribute):
    """Cancelling some other subscription used to close every row the user
    had, the lifetime purchase included, because none matched its id."""
    tribute.send("new_digital_product", product_id=PRODUCT)
    tribute.send("cancelled_subscription", created_at="2026-09-02T10:00:00.000000Z",
                 subscription_id=SUBSCRIPTION)
    assert tribute.access() is True
    assert tribute.subscriptions()[PRODUCT].status == "active"


def test_a_cancellation_cannot_shorten_a_purchase_that_never_ends(tribute):
    tribute.send("new_digital_product", product_id=PRODUCT)
    tribute.send("cancelled_subscription", created_at="2026-09-02T10:00:00.000000Z",
                 product_id=PRODUCT)
    assert tribute.access() is True
    assert tribute.subscriptions()[PRODUCT].status == "active"


def test_a_refund_still_ends_access_at_once(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send("refund", created_at="2026-09-02T10:00:00.000000Z",
                 subscription_id=SUBSCRIPTION)
    assert tribute.access() is False
    assert tribute.subscriptions()[SUBSCRIPTION].status == "refunded"


def test_a_chargeback_ends_access_at_once_and_is_filed_as_one(tribute):
    """It used to be filed as "canceled", which now means "paid until"."""
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send("chargeback", created_at="2026-09-02T10:00:00.000000Z",
                 subscription_id=SUBSCRIPTION)
    assert tribute.access() is False
    assert tribute.subscriptions()[SUBSCRIPTION].status == "charged_back"


def test_a_refund_after_a_cancellation_ends_the_rest_of_the_period(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send("cancelled_subscription", created_at="2026-09-02T10:00:00.000000Z",
                 subscription_id=SUBSCRIPTION)
    assert tribute.access() is True
    tribute.send("refund", created_at="2026-09-03T10:00:00.000000Z",
                 subscription_id=SUBSCRIPTION)
    assert tribute.access() is False


def test_a_chargeback_filed_as_a_cancellation_by_the_old_code_stays_revoked(tribute):
    """Rows the old code wrote: a chargeback of a lifetime purchase was left
    "canceled" with no expiry. A cancellation grants access only until an
    expiry, so these must not come back."""
    tribute.send("new_digital_product", product_id=PRODUCT)

    async def as_the_old_code_left_it() -> None:
        async with database.get_db() as session:
            row = (await session.execute(select(Subscription))).scalar_one()
            row.status = "canceled"

    tribute.client.portal.call(as_the_old_code_left_it)
    assert tribute.access() is False


# ---------------------------------------------------------------------------
# B-08: the order events happened in, not the order they arrived in
# ---------------------------------------------------------------------------

T1 = "2026-09-01T10:00:00.000000Z"
T2 = "2026-09-02T10:00:00.000000Z"
T3 = "2026-09-03T10:00:00.000000Z"


def notes(tribute: Tribute) -> list[str]:
    async def read() -> list[str]:
        async with database.get_db() as session:
            found = (await session.execute(select(WebhookEvent))).scalars().all()
            return [row.error or "" for row in found]

    return tribute.client.portal.call(read)


def test_the_row_keeps_when_its_event_happened_not_when_it_arrived(tribute):
    tribute.send("new_digital_product", created_at=T1, sent_at=T3, product_id=PRODUCT)
    assert tribute.subscriptions()[PRODUCT].last_event_at == datetime(2026, 9, 1, 10, 0)


def test_an_unreadable_sent_at_does_not_lose_when_the_event_happened(tribute):
    body = tribute.body("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.post(body.replace(b'"sent_at": "' + T1.encode(), b'"sent_at": "yesterday'))
    assert tribute.subscriptions()[PRODUCT].last_event_at == datetime(2026, 9, 1, 10, 0)


def test_a_purchase_retried_after_its_refund_grants_nothing(tribute):
    """Tribute retries for about a day, and a customer can be refunded
    within it: the retry must not buy the access back."""
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.send("digital_product_refunded", created_at=T2, product_id=PRODUCT)
    assert tribute.access() is False

    tribute.send("new_digital_product", created_at=T1, sent_at=T3, product_id=PRODUCT)
    assert tribute.access() is False
    assert tribute.subscriptions()[PRODUCT].status == "refunded"


def test_a_purchase_first_delivered_after_its_refund_grants_nothing(tribute):
    """The refund came first (the purchase's first attempt failed): it is
    remembered under the product it names, and the purchase is older."""
    tribute.send("digital_product_refunded", created_at=T2, product_id=PRODUCT)
    answer = tribute.send("new_digital_product", created_at=T1, sent_at=T3, product_id=PRODUCT)
    assert answer["message"] == "Stale event ignored"
    assert answer["action"] == "ignore"
    assert tribute.access() is False
    assert any(note.startswith("stale event ignored") for note in notes(tribute))


def test_an_older_chargeback_does_not_undo_a_newer_purchase(tribute):
    """Bought, refunded, bought again - and then a chargeback of the first
    purchase arrives. The second purchase stands."""
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.send("digital_product_refunded", created_at="2026-09-01T12:00:00.000000Z",
                 product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T3, product_id=PRODUCT)
    assert tribute.access() is True

    answer = tribute.send("chargeback", created_at=T2, product_id=PRODUCT)
    assert answer["action"] == "ignore"
    assert tribute.access() is True


def test_an_older_cancellation_does_not_end_a_newer_renewal(tribute):
    first_period_end = iso(datetime.utcnow() - timedelta(days=1))
    tribute.send("new_subscription", created_at=T1, subscription_id=SUBSCRIPTION,
                 expires_at=first_period_end)
    tribute.send("renewed_subscription", created_at=T3, subscription_id=SUBSCRIPTION,
                 expires_at=LATER)
    tribute.send("cancelled_subscription", created_at=T2, subscription_id=SUBSCRIPTION,
                 expires_at=first_period_end)
    assert tribute.access() is True
    row = tribute.subscriptions()[SUBSCRIPTION]
    assert row.status == "active" and row.last_event_at == datetime(2026, 9, 3, 10, 0)


def test_a_stale_event_is_recorded_once_and_not_journaled(tribute):
    tribute.send("digital_product_refunded", created_at=T2, product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)

    async def journal() -> list[str]:
        async with database.get_db() as session:
            found = (await session.execute(select(Payment))).scalars().all()
            return [row.event_name for row in found]

    assert tribute.client.portal.call(journal) == ["digital_product_refunded"]
    assert len(notes(tribute)) == 2, "both deliveries are on record"
