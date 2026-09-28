"""What a Tribute event means, in whatever order and however often it arrives.

tests/test_webhook_contract.py holds the shape of a delivery and its
signature. This file holds its meaning, finding by finding of the September
2026 backend audit:

* B-09 - a cancellation switches the renewal off; the period already paid
  for runs to its end. Refunds and chargebacks still revoke at once.
* B-08 - events are applied in the order they happened, not the order
  they arrived: one older than the last event applied to that access is
  acknowledged, recorded, and changes nothing.
* B-07 - an event is processed once however often it is delivered: a
  redelivery with a new `sent_at` is a duplicate, a gift purchase mints one
  certificate, and its code is sent only after the certificate is saved.
* B-06 - a refunded gift revokes the certificate it paid for, redeemed or
  not, and leaves the buyer's own access alone.

Every delivery here is signed the way Tribute signs it, and access is read
back through `user_has_access`, the one function that decides it.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.models import Certificate, Payment, Subscription, WebhookEvent
from vechnost_bot.payments.services import activate_certificate, user_has_access
from vechnost_bot.payments.tribute_event import TributeEvent, action_for
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
        return json.dumps(
            {
                "name": name,
                "created_at": created_at,
                "sent_at": sent_at or created_at,
                "payload": {
                    "telegram_user_id": telegram_user_id,
                    "amount": 990,
                    "currency": "eur",
                    **payload,
                },
            }
        ).encode()

    def post(self, body: bytes) -> dict[str, Any]:
        signature = hmac.new(API_KEY.encode(), body, hashlib.sha256).hexdigest()
        response = self.client.post(
            "/webhooks/tribute",
            content=body,
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
    answer = tribute.send(
        "cancelled_subscription",
        created_at="2026-09-02T10:00:00.000000Z",
        subscription_id=SUBSCRIPTION,
        expires_at=LATER,
    )
    assert answer["action"] == "cancel"
    assert tribute.access() is True, "paid for twenty more days"
    row = tribute.subscriptions()[SUBSCRIPTION]
    assert row.status == "canceled"
    assert row.expires_at is not None and row.expires_at > datetime.utcnow()


def test_a_cancellation_whose_period_is_over_ends_access(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    yesterday = iso(datetime.utcnow() - timedelta(days=1))
    tribute.send(
        "cancelled_subscription",
        created_at="2026-09-02T10:00:00.000000Z",
        subscription_id=SUBSCRIPTION,
        expires_at=yesterday,
    )
    assert tribute.access() is False, "Tribute says the paid period ended yesterday"


def test_a_cancellation_does_not_touch_a_lifetime_purchase(tribute):
    """Cancelling some other subscription used to close every row the user
    had, the lifetime purchase included, because none matched its id."""
    tribute.send("new_digital_product", product_id=PRODUCT)
    tribute.send(
        "cancelled_subscription",
        created_at="2026-09-02T10:00:00.000000Z",
        subscription_id=SUBSCRIPTION,
    )
    assert tribute.access() is True
    assert tribute.subscriptions()[PRODUCT].status == "active"


def test_a_cancellation_cannot_shorten_a_purchase_that_never_ends(tribute):
    tribute.send("new_digital_product", product_id=PRODUCT)
    tribute.send(
        "cancelled_subscription", created_at="2026-09-02T10:00:00.000000Z", product_id=PRODUCT
    )
    assert tribute.access() is True
    assert tribute.subscriptions()[PRODUCT].status == "active"


def test_a_refund_still_ends_access_at_once(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send("refund", created_at="2026-09-02T10:00:00.000000Z", subscription_id=SUBSCRIPTION)
    assert tribute.access() is False
    assert tribute.subscriptions()[SUBSCRIPTION].status == "refunded"


def test_a_chargeback_ends_access_at_once_and_is_filed_as_one(tribute):
    """It used to be filed as "canceled", which now means "paid until"."""
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send(
        "chargeback", created_at="2026-09-02T10:00:00.000000Z", subscription_id=SUBSCRIPTION
    )
    assert tribute.access() is False
    assert tribute.subscriptions()[SUBSCRIPTION].status == "charged_back"


def test_a_refund_after_a_cancellation_ends_the_rest_of_the_period(tribute):
    tribute.send("new_subscription", subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send(
        "cancelled_subscription",
        created_at="2026-09-02T10:00:00.000000Z",
        subscription_id=SUBSCRIPTION,
    )
    assert tribute.access() is True
    tribute.send("refund", created_at="2026-09-03T10:00:00.000000Z", subscription_id=SUBSCRIPTION)
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
    tribute.send(
        "digital_product_refunded", created_at="2026-09-01T12:00:00.000000Z", product_id=PRODUCT
    )
    tribute.send("new_digital_product", created_at=T3, product_id=PRODUCT)
    assert tribute.access() is True

    answer = tribute.send("chargeback", created_at=T2, product_id=PRODUCT)
    assert answer["action"] == "ignore"
    assert tribute.access() is True


def test_an_older_cancellation_does_not_end_a_newer_renewal(tribute):
    first_period_end = iso(datetime.utcnow() - timedelta(days=1))
    tribute.send(
        "new_subscription", created_at=T1, subscription_id=SUBSCRIPTION, expires_at=first_period_end
    )
    tribute.send(
        "renewed_subscription", created_at=T3, subscription_id=SUBSCRIPTION, expires_at=LATER
    )
    tribute.send(
        "cancelled_subscription",
        created_at=T2,
        subscription_id=SUBSCRIPTION,
        expires_at=first_period_end,
    )
    assert tribute.access() is True
    row = tribute.subscriptions()[SUBSCRIPTION]
    assert row.status == "active" and row.last_event_at == datetime(2026, 9, 3, 10, 0)


def journal(tribute: Tribute) -> list[str]:
    """The event names in the payments journal, oldest first."""

    async def read() -> list[str]:
        async with database.get_db() as session:
            found = (await session.execute(select(Payment).order_by(Payment.id))).scalars().all()
            return [row.event_name for row in found]

    return tribute.client.portal.call(read)


def test_a_stale_event_is_recorded_once_and_not_journaled(tribute):
    tribute.send("digital_product_refunded", created_at=T2, product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    assert journal(tribute) == ["digital_product_refunded"]
    assert len(notes(tribute)) == 2, "both deliveries are on record"


# ---------------------------------------------------------------------------
# B-07: one event, however many deliveries
# ---------------------------------------------------------------------------

GIFT = 999


@pytest.fixture
def gifts(tribute) -> Iterator[AsyncMock]:
    """The gift product configured; what reaches the buyer's chat, recorded."""
    with (
        patch.object(settings, "gift_product_id", str(GIFT)),
        patch(
            "vechnost_bot.payments.services.deliver_gift_certificate", new_callable=AsyncMock
        ) as sent,
    ):
        yield sent


def certificates(tribute: Tribute) -> list[Certificate]:
    async def read() -> list[Certificate]:
        async with database.get_db() as session:
            found = await session.execute(select(Certificate).order_by(Certificate.id))
            return list(found.scalars().all())

    return tribute.client.portal.call(read)


def test_the_event_key_ignores_the_attempt_and_hides_the_buyer():
    def key(**body: Any) -> str | None:
        return TributeEvent.parse(
            {
                "name": "new_subscription",
                "created_at": T1,
                "sent_at": T1,
                "payload": {"telegram_user_id": BUYER, "subscription_id": SUBSCRIPTION},
                **body,
            }
        ).idempotency_key

    first = key()
    assert first and len(first) == 64 and str(BUYER) not in first
    assert key(sent_at=T3) == first, "a retry is the same event"
    assert key(created_at=T2) != first, "another renewal is another event"
    assert key(created_at=None) is None, "nothing stable to key on: the body decides"

    def purchase(**body: Any) -> str | None:
        return TributeEvent.parse(
            {
                "name": "new_digital_product",
                "created_at": T1,
                "payload": {"telegram_user_id": BUYER, "product_id": GIFT, "purchase_id": 31337},
                **body,
            }
        ).idempotency_key

    assert purchase(created_at=T2) == purchase(), "a purchase is named by its id"
    assert purchase(name="digital_product_refunded") != purchase()


def test_a_redelivery_with_a_new_sent_at_is_the_same_event(tribute):
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    again = tribute.send("new_digital_product", created_at=T1, sent_at=T3, product_id=PRODUCT)
    assert "already processed" in again["message"]
    assert journal(tribute) == ["new_digital_product"]
    assert len(notes(tribute)) == 1


def test_two_purchases_at_two_moments_are_two_events(tribute):
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T2, product_id=PRODUCT)
    assert journal(tribute) == ["new_digital_product", "new_digital_product"]


def test_a_retried_gift_purchase_mints_one_certificate(tribute, gifts):
    for sent_at in (T1, "2026-09-01T10:05:00.000000Z", "2026-09-01T11:00:00.000000Z"):
        tribute.send("new_digital_product", created_at=T1, sent_at=sent_at, product_id=GIFT)
    [certificate] = certificates(tribute)
    gifts.assert_awaited_once()
    assert gifts.await_args.args[1] == certificate.code


def test_a_gift_purchase_mints_one_certificate_whatever_its_timestamps(tribute, gifts):
    tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=4242)
    tribute.send("new_digital_product", created_at=T2, product_id=GIFT, purchase_id=4242)
    [certificate] = certificates(tribute)
    assert certificate.purchase_id == "4242"
    gifts.assert_awaited_once()


def test_two_gift_purchases_are_two_certificates(tribute, gifts):
    tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=1)
    tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=2)
    assert [c.purchase_id for c in certificates(tribute)] == ["1", "2"]
    assert gifts.await_count == 2


def test_the_gift_code_is_sent_only_once_the_certificate_is_saved(tribute, gifts):
    """The old code sent the code from inside the transaction: when the
    commit then failed, the buyer held a code for a certificate that was
    rolled back, and Tribute's retry minted and sent a second one."""
    from sqlalchemy.exc import IntegrityError

    import vechnost_bot.payments.services as services

    body = tribute.body("new_digital_product", product_id=GIFT)
    signature = hmac.new(API_KEY.encode(), body, hashlib.sha256).hexdigest()
    with patch.object(
        services.WebhookEventRepository,
        "create",
        side_effect=IntegrityError("INSERT", {}, Exception("lost")),
    ):
        response = tribute.client.post(
            "/webhooks/tribute",
            content=body,
            headers={"Content-Type": "application/json", "trbt-signature": signature},
        )
    assert response.status_code == 503, "not applied, so Tribute sends it again"
    gifts.assert_not_awaited()
    assert certificates(tribute) == []

    tribute.post(body)
    [certificate] = certificates(tribute)
    gifts.assert_awaited_once()
    assert gifts.await_args.args[1] == certificate.code


def test_a_redelivery_racing_the_first_is_turned_away_by_the_database(tribute, gifts):
    """Both copies looked before either had committed. The event key is
    unique, so the second copy's insert fails and its certificate goes with
    its rolled-back transaction."""
    import vechnost_bot.payments.services as services

    tribute.send("new_digital_product", created_at=T1, product_id=GIFT)
    with patch.object(
        services.WebhookEventRepository, "get_by_event_key", side_effect=[None, object()]
    ):
        again = tribute.send("new_digital_product", created_at=T1, sent_at=T3, product_id=GIFT)
    assert again["message"] == "Webhook already processed (race condition)"
    assert len(certificates(tribute)) == 1
    gifts.assert_awaited_once()


def test_an_old_database_gets_the_event_key_and_the_purchase_link(tmp_path):
    """Deploys run create_all, which never alters a table: the startup step
    adds both columns and their unique indexes to tables made without them."""
    from sqlalchemy.exc import IntegrityError

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(OLD_PAYMENT_TABLES)

    async def restart_and_insert_twice() -> None:
        try:
            await database.create_tables()
            await database.create_tables()  # and the restart after it
            async with database.get_db() as session:
                session.add(Certificate(code="VECH-AAAA-AAAA", purchase_id="7"))
            with pytest.raises(IntegrityError):
                async with database.get_db() as session:
                    session.add(Certificate(code="VECH-BBBB-BBBB", purchase_id="7"))
        finally:
            await database.close_db()

    with (
        patch.object(settings, "database_url", f"sqlite:///{path}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        asyncio.run(restart_and_insert_twice())

    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(webhook_events)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(webhook_events)")}
        certificate_columns = {row[1] for row in conn.execute("PRAGMA table_info(certificates)")}
    assert "event_key" in columns and "uq_webhook_events_event_key" in indexes
    assert {"purchase_id", "revoked_at"} <= certificate_columns


# ---------------------------------------------------------------------------
# B-06: a gift's refund takes the gift back, not the buyer's access
# ---------------------------------------------------------------------------

FRIEND = 626262  # who the gift was for


def redeem(tribute: Tribute, code: str, telegram_user_id: int = FRIEND) -> dict[str, Any]:
    return tribute.client.portal.call(activate_certificate, code, telegram_user_id)


def test_a_gift_refund_leaves_the_buyers_own_access_alone(tribute, gifts):
    """The buyer's own purchase used to be closed, because the refund named
    the gift product and the fallback closed every row that matched nothing."""
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T2, product_id=GIFT, purchase_id=900)
    tribute.send("digital_product_refunded", created_at=T3, product_id=GIFT, purchase_id=900)
    assert tribute.access() is True
    assert tribute.subscriptions()[PRODUCT].status == "active"


@pytest.mark.parametrize("refund", ["digital_product_refunded", "chargeback"])
def test_a_gift_refund_revokes_the_certificate_even_once_redeemed(tribute, gifts, refund):
    tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=900)
    [certificate] = certificates(tribute)
    assert redeem(tribute, certificate.code)["status"] == "success"
    assert tribute.access(FRIEND) is True

    answer = tribute.send(refund, created_at=T2, product_id=GIFT, purchase_id=900)
    assert answer["action"] == "revoke"
    assert tribute.access(FRIEND) is False, "the money went back, so did the gift"
    [certificate] = certificates(tribute)
    assert certificate.revoked_at is not None


def test_a_revoked_certificate_cannot_be_redeemed(tribute, gifts):
    tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=900)
    tribute.send("digital_product_refunded", created_at=T2, product_id=GIFT, purchase_id=900)
    [certificate] = certificates(tribute)
    answer = redeem(tribute, certificate.code)
    assert (answer["status"], answer["code"]) == ("error", 410)
    assert tribute.access(FRIEND) is False


def test_a_gift_refund_is_found_by_its_purchase_id_alone(tribute, gifts):
    """A refund that does not repeat the product id is still the gift's."""
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T2, product_id=GIFT, purchase_id=900)
    tribute.send("refund", created_at=T3, purchase_id=900)
    assert tribute.access() is True
    assert certificates(tribute)[0].revoked_at is not None


def test_a_gift_refund_that_names_no_purchase_changes_nothing(tribute, gifts, caplog):
    tribute.send("new_digital_product", created_at=T1, product_id=PRODUCT)
    tribute.send("new_digital_product", created_at=T2, product_id=GIFT)
    answer = tribute.send("digital_product_refunded", created_at=T3, product_id=GIFT)
    assert answer["note"] == "gift refund not applied: the purchase could not be identified"
    assert tribute.access() is True
    assert certificates(tribute)[0].revoked_at is None
    assert "no certificate can be matched" in caplog.text


def test_a_gift_refunded_before_its_purchase_arrives_mints_nothing(tribute, gifts):
    tribute.send("digital_product_refunded", created_at=T2, product_id=GIFT, purchase_id=900)
    answer = tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=900)
    assert answer["note"] == "gift purchase already refunded: no certificate issued"
    gifts.assert_not_awaited()
    [placeholder] = certificates(tribute)
    assert placeholder.revoked_at is not None
    assert redeem(tribute, placeholder.code)["code"] == 410


def test_a_refund_of_access_the_buyer_does_not_hold_is_logged_as_an_anomaly(tribute, caplog):
    """The fallback stays for the buyer's own purchases - a refund with no
    effect is worse than one with too much - but it is not normal."""
    tribute.send("new_subscription", created_at=T1, subscription_id=SUBSCRIPTION, expires_at=LATER)
    tribute.send("digital_product_refunded", created_at=T2, product_id=PRODUCT)
    assert tribute.access() is False
    assert "Anomaly" in caplog.text


def test_erasing_the_buyer_does_not_make_the_gift_irrevocable(tribute, gifts):
    """/delete_me takes the buyer's journal; the certificate keeps the id of
    the purchase that paid for it, so its refund still finds it."""
    from vechnost_bot.payments.repositories import UserRepository

    tribute.send("new_digital_product", created_at=T1, product_id=GIFT, purchase_id=900)
    [certificate] = certificates(tribute)
    redeem(tribute, certificate.code)

    async def erase_buyer() -> None:
        async with database.get_db() as session:
            await UserRepository.erase(session, BUYER)

    tribute.client.portal.call(erase_buyer)
    tribute.send("digital_product_refunded", created_at=T2, product_id=GIFT, purchase_id=900)
    assert tribute.access(FRIEND) is False


# The two tables as the code before these columns created them.
OLD_PAYMENT_TABLES = (
    "CREATE TABLE webhook_events (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL,"
    " sent_at DATETIME NOT NULL, created_at DATETIME NOT NULL,"
    " body_sha256 VARCHAR NOT NULL UNIQUE, status_code INTEGER NOT NULL,"
    " processed_at DATETIME, error TEXT);"
    "CREATE TABLE certificates (id INTEGER PRIMARY KEY, code VARCHAR NOT NULL UNIQUE,"
    " is_used BOOLEAN NOT NULL, used_by_telegram_user_id BIGINT, used_at DATETIME,"
    " created_at DATETIME NOT NULL);"
)
