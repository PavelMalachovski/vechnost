"""Referral links: minting a code, crediting an invite, and the cheaper price."""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot import referrals
from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import UserRepository


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'ref.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def _user(telegram_user_id, name="U"):
    async with get_db() as session:
        await UserRepository.create_or_update(
            session, telegram_user_id=telegram_user_id, first_name=name
        )


# ---------------------------------------------------------------------------
# The code itself
# ---------------------------------------------------------------------------

def test_a_code_is_stable_for_the_same_seed():
    """A retry after a lost response must not burn a fresh code."""
    assert referrals.code_from_seed("42:0") == referrals.code_from_seed("42:0")


def test_two_users_get_two_codes():
    assert referrals.code_from_seed("42:0") != referrals.code_from_seed("43:0")


def test_a_code_avoids_the_characters_people_misread():
    """0/O and 1/I are the pairs that get confused; the alphabet drops all
    four. Asserted on the alphabet, not on one generated code: a code that
    happens not to contain an L passes either way, so the old form was
    testing the seed rather than the rule."""
    assert len(referrals.code_from_seed("whatever:0")) == referrals.CODE_LENGTH
    assert not (set(referrals.CODE_ALPHABET) & set("01OI"))


def test_a_code_gives_nothing_away_about_the_account():
    """Hashed, not encoded: a code is shared publicly and must not carry a
    telegram id anyone could read back out of it."""
    assert "12345" not in referrals.code_from_seed("12345:0")


def test_a_code_is_read_back_however_it_was_typed():
    assert referrals.normalize("  abc234 ") == "ABC234"
    assert referrals.normalize("ABC234") == "ABC234"


def test_something_that_is_not_a_code_is_refused():
    assert referrals.normalize("") is None
    assert referrals.normalize("ABC") is None          # too short
    assert referrals.normalize("ABC2345") is None      # too long
    assert referrals.normalize("AB0234") is None       # a zero is not in the alphabet


def test_only_a_referral_deep_link_is_read_as_one():
    assert referrals.parse_start_param("ref_ABC234") == "ABC234"
    assert referrals.parse_start_param("activate_ABC234") is None
    assert referrals.parse_start_param("ref_") is None
    assert referrals.parse_start_param(None) is None


def test_the_link_carries_the_bot_handle():
    with patch.object(settings, "bot_username", "somebot"):
        assert referrals.invite_link("ABC234") == "https://t.me/somebot?start=ref_ABC234"
    with patch.object(settings, "bot_username", None):
        assert referrals.invite_link("ABC234") is None


# ---------------------------------------------------------------------------
# Minting and crediting
# ---------------------------------------------------------------------------

async def test_a_code_is_minted_once_and_then_stays(db):
    await _user(1)
    async with get_db() as session:
        first = await UserRepository.ensure_referral_code(session, 1)
    async with get_db() as session:
        second = await UserRepository.ensure_referral_code(session, 1)
    assert first and first == second


async def test_an_unknown_user_gets_no_code(db):
    async with get_db() as session:
        assert await UserRepository.ensure_referral_code(session, 999) is None


async def test_following_a_link_credits_the_inviter(db):
    await _user(1, "Inviter")
    await _user(2, "Invitee")
    async with get_db() as session:
        code = await UserRepository.ensure_referral_code(session, 1)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 2, code) is True
    async with get_db() as session:
        assert await UserRepository.is_referred(session, 2) is True
        assert await UserRepository.count_referrals(session, 1) == 1
        invitee = await UserRepository.get_by_telegram_id(session, 2)
        assert invitee.referred_by == 1
        assert invitee.referred_at is not None, "the invitee's own marker"


async def test_invitations_made_before_the_marker_keep_their_discount(db):
    """A database from before `referred_at` gets the column at startup, and
    everyone already invited is marked in the same step. Without that, the
    deploy that added the marker would have taken the discount from every
    invitee at once."""
    from sqlalchemy import text

    await _user(1, "Inviter")
    await _user(2, "Invitee")
    await _user(3, "Nobody")
    async with get_db() as session:
        code = await UserRepository.ensure_referral_code(session, 1)
        await UserRepository.record_referral(session, 2, code)

    # Back to the schema before the marker: the column gone, the link kept.
    engine = database._engine()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users DROP COLUMN referred_at"))
    await database.create_tables()

    async with get_db() as session:
        assert await UserRepository.is_referred(session, 2) is True
        assert await UserRepository.is_referred(session, 3) is False
        invitee = await UserRepository.get_by_telegram_id(session, 2)
        assert invitee.referred_at == invitee.created_at
    await database.close_db()


async def test_nobody_can_follow_their_own_link(db):
    await _user(1)
    async with get_db() as session:
        code = await UserRepository.ensure_referral_code(session, 1)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 1, code) is False
        assert await UserRepository.is_referred(session, 1) is False


async def test_the_first_invitation_keeps_the_credit(db):
    """A second link must not reassign someone who has already been invited."""
    await _user(1)
    await _user(2)
    await _user(3)
    async with get_db() as session:
        first = await UserRepository.ensure_referral_code(session, 1)
        second = await UserRepository.ensure_referral_code(session, 2)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 3, first) is True
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 3, second) is False
    async with get_db() as session:
        assert await UserRepository.count_referrals(session, 1) == 1
        assert await UserRepository.count_referrals(session, 2) == 0


async def _age(telegram_user_id, minutes):
    """Pretend this user registered `minutes` ago."""
    from datetime import datetime, timedelta

    async with get_db() as session:
        user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
        user.created_at = datetime.utcnow() - timedelta(minutes=minutes)


async def _inviters_code():
    await _user(1, "Inviter")
    async with get_db() as session:
        return await UserRepository.ensure_referral_code(session, 1)


async def test_an_account_that_was_already_here_is_not_credited(db):
    """Any published link used to hand the referral price to anyone who had
    been using the bot for months, and count them as the inviter's catch."""
    code = await _inviters_code()
    await _user(2, "Regular")
    await _age(2, minutes=60 * 24 * 30)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 2, code) is False
    async with get_db() as session:
        assert await UserRepository.is_referred(session, 2) is False
        assert await UserRepository.count_referrals(session, 1) == 0


@pytest.mark.parametrize("past_the_window, credited", [(-1, True), (1, False)])
async def test_the_newcomer_window_is_a_few_minutes(db, past_the_window, credited):
    """The /start that carries the code registers the user a moment before
    crediting them; the window is slack for that, not a grace period."""
    window = int(referrals.NEW_USER_WINDOW.total_seconds() // 60)
    assert 0 < window <= 15, "a few minutes, not a trial period"
    code = await _inviters_code()
    await _user(2, "Newcomer")
    await _age(2, minutes=window + past_the_window)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 2, code) is credited


@pytest.mark.parametrize("history", ["payment", "subscription", "certificate"])
async def test_someone_who_already_bought_is_not_credited(db, history):
    """A customer is not somebody the link brought in, however new the row:
    the webhook creates it on the purchase, a certificate on activation."""
    from vechnost_bot.payments.repositories import (
        CertificateRepository,
        PaymentRepository,
        SubscriptionRepository,
    )

    code = await _inviters_code()
    await _user(2, "Customer")
    async with get_db() as session:
        user = await UserRepository.get_by_telegram_id(session, 2)
        if history == "payment":
            await PaymentRepository.create(
                session, provider="tribute", event_name="new_digital_product",
                user_id=user.id, telegram_user_id=2, amount=49900, currency="rub",
                raw_body={}, signature="", body_sha256="ref-history",
            )
        elif history == "subscription":
            await SubscriptionRepository.upsert(
                session, user_id=user.id, subscription_id=0, period="lifetime",
                status="canceled", expires_at=None,
            )
        else:
            certificate = await CertificateRepository.create(session, code="REF-HISTORY-TEST")
            await CertificateRepository.mark_as_used(session, certificate, 2)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 2, code) is False
        assert await UserRepository.is_referred(session, 2) is False


async def test_a_code_nobody_owns_credits_nobody(db):
    await _user(2)
    async with get_db() as session:
        assert await UserRepository.record_referral(session, 2, "ZZZZZZ") is False


async def test_an_unreferred_user_is_not_referred(db):
    await _user(7)
    async with get_db() as session:
        assert await UserRepository.is_referred(session, 7) is False
        assert await UserRepository.count_referrals(session, 7) == 0


# ---------------------------------------------------------------------------
# The discount
# ---------------------------------------------------------------------------

def test_the_discount_needs_a_page_to_send_people_to():
    """Tribute owns the price, so with no discounted product configured the
    referral is still recorded and everyone pays the same."""
    with patch.object(settings, "referral_payment_url", None):
        assert referrals.discount_available() is False
        assert referrals.payment_url_for(referred=True) is None


def test_a_referred_user_is_sent_to_the_cheaper_page():
    with patch.object(settings, "referral_payment_url", "https://tribute.to/ten-off"):
        assert referrals.discount_available() is True
        assert referrals.payment_url_for(referred=True) == "https://tribute.to/ten-off"


def test_an_ordinary_user_is_not():
    with patch.object(settings, "referral_payment_url", "https://tribute.to/ten-off"):
        assert referrals.payment_url_for(referred=False) is None


async def test_the_paywall_sends_a_referred_user_to_the_discounted_page(db):
    """The whole of the discount is which of two Tribute pages the client is
    handed, so this is the test that the feature works at all."""
    from fastapi.testclient import TestClient

    from vechnost_bot.payments.web import app

    await _user(1, "Inviter")
    await _user(2, "Invitee")
    async with get_db() as session:
        code = await UserRepository.ensure_referral_code(session, 1)
    async with get_db() as session:
        await UserRepository.record_referral(session, 2, code)

    def paywall(user_id):
        with (
            patch.object(settings, "enable_payment", True),
            patch.object(settings, "referral_payment_url", "https://tribute.to/ten-off"),
            patch.object(settings, "tribute_payment_url", "https://tribute.to/full"),
            patch(
                "vechnost_bot.payments.web.validate_init_data",
                return_value={"user": {"id": user_id, "first_name": "X"}},
            ),
            patch("vechnost_bot.payments.web.user_has_access", return_value=False),
        ):
            return TestClient(app).get(
                "/api/questions", headers={"Authorization": "tma x"}
            ).json()["access"]

    invited = paywall(2)
    assert invited["payment_url"] == "https://tribute.to/ten-off"
    assert invited["discount_percent"] == settings.referral_discount_percent

    ordinary = paywall(1)
    assert ordinary["payment_url"] == "https://tribute.to/full"
    assert "discount_percent" not in ordinary


async def test_no_discounted_page_means_no_promise_of_one(db):
    """Never tell someone the price is lower when it is the same link."""
    from fastapi.testclient import TestClient

    from vechnost_bot.payments.web import app

    await _user(1)
    await _user(2)
    async with get_db() as session:
        code = await UserRepository.ensure_referral_code(session, 1)
    async with get_db() as session:
        await UserRepository.record_referral(session, 2, code)

    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "referral_payment_url", None),
        patch.object(settings, "tribute_payment_url", "https://tribute.to/full"),
        patch(
            "vechnost_bot.payments.web.validate_init_data",
            return_value={"user": {"id": 2, "first_name": "X"}},
        ),
        patch("vechnost_bot.payments.web.user_has_access", return_value=False),
    ):
        access = TestClient(app).get(
            "/api/questions", headers={"Authorization": "tma x"}
        ).json()["access"]

    assert access["payment_url"] == "https://tribute.to/full"
    assert "discount_percent" not in access
