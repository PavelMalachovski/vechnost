"""What a Tribute event means, in whatever order and however often it arrives.

tests/test_webhook_contract.py holds the shape of a delivery and its
signature. This file holds its meaning, finding by finding of the September
2026 backend audit:

* B-09 - a cancellation switches the renewal off; the period already paid
  for runs to its end. Refunds and chargebacks still revoke at once.

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
from vechnost_bot.payments.models import Subscription
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
