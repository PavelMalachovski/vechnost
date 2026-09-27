"""The access backfill serves the customers it was written for, and nobody else.

`user_has_access` once counted any undated `payments` row as lifetime access;
it now reads `subscriptions` only, and a startup step gives every customer
whose access rested on such a payment the equivalent subscription. Written
as "once", it re-read the whole journal on every start: a gift bought for
someone else and a chargeback are undated `payments` rows too, so the next
restart handed their authors lifetime access (backend audit B-02). And on
PostgreSQL it had never run at all - a typing error on every start (B-01),
covered by tests/test_postgres.py.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.repositories import PaymentRepository, UserRepository
from vechnost_bot.payments.services import user_has_access

CUTOVER = datetime.fromisoformat(database.ACCESS_FROM_PAYMENTS_CUTOVER)
LEGACY_BUYER = 910_001
GIFT_BUYER = 910_002
CHARGEBACK = 910_003


@pytest.fixture
async def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'backfill.db'}"),
        patch.object(settings, "enable_payment", True),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield
        await database.close_db()


async def _journal(telegram_user_id: int, event: str, when: datetime) -> None:
    """An undated `payments` row, as the webhook handler writes one."""
    async with database.get_db() as session:
        user = await UserRepository.create_or_update(session, telegram_user_id)
        payment = await PaymentRepository.create(
            session,
            provider="tribute",
            event_name=event,
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            amount=49900,
            currency="rub",
            raw_body={"name": event},
            signature="e2e",
            body_sha256=f"{telegram_user_id}-{event}-{when.isoformat()}",
        )
        payment.created_at = when


async def _subscriptions(telegram_user_id: int) -> int:
    from sqlalchemy import func, select

    from vechnost_bot.payments.models import Subscription, User

    async with database.get_db() as session:
        result = await session.execute(
            select(func.count()).select_from(Subscription).join(User)
            .where(User.telegram_user_id == telegram_user_id)
        )
        return int(result.scalar_one())


async def test_legacy_payments_become_access_once_and_new_journal_rows_never(db):
    await _journal(LEGACY_BUYER, "new_digital_product", CUTOVER - timedelta(days=30))
    await _journal(GIFT_BUYER, "new_digital_product", CUTOVER + timedelta(days=3))
    await _journal(CHARGEBACK, "chargeback", CUTOVER + timedelta(days=5))

    for _restart in range(3):
        await database.create_tables()

    assert await user_has_access(LEGACY_BUYER) is True
    assert await _subscriptions(LEGACY_BUYER) == 1, "backfilled once, not once per start"
    assert await user_has_access(GIFT_BUYER) is False, "a gift is the recipient's access"
    assert await user_has_access(CHARGEBACK) is False, "a chargeback grants nothing"
    assert await _subscriptions(GIFT_BUYER) == await _subscriptions(CHARGEBACK) == 0
