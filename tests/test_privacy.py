"""`/delete_me` forgets a person: the rows, the partner rows, the session."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import vechnost_bot.payments.database as database
from vechnost_bot import privacy
from vechnost_bot.config import settings
from vechnost_bot.i18n import Language, get_text
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.models import (
    Certificate,
    CompatTest,
    Payment,
    Room,
    Steps69Game,
    Subscription,
    User,
)
from vechnost_bot.payments.repositories import (
    CertificateRepository,
    CompatTestRepository,
    PaymentRepository,
    RoomRepository,
    Steps69Repository,
    SubscriptionRepository,
    UserRepository,
)
from vechnost_bot.payments.services import user_has_access

ME = 4242
PARTNER = 4343
INVITED = 4444


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


async def _rows(model):
    async with get_db() as session:
        return list((await session.execute(select(model))).scalars().all())


async def _populate():
    async with get_db() as session:
        me = await UserRepository.create_or_update(session, telegram_user_id=ME, username="me")
        await UserRepository.create_or_update(session, telegram_user_id=PARTNER)
        await UserRepository.create_or_update(session, telegram_user_id=INVITED)
        await UserRepository.ensure_referral_code(session, ME)
        code = me.referral_code
        await UserRepository.record_referral(session, INVITED, code)

        await SubscriptionRepository.upsert(
            session, user_id=me.id, subscription_id=0, period="lifetime",
            status="active", expires_at=None,
        )
        await PaymentRepository.create(
            session, provider="tribute", event_name="new_digital_product",
            user_id=me.id, telegram_user_id=ME, amount=990, currency="eur",
            raw_body={"payload": {"telegram_user_id": ME}}, signature="", body_sha256="p1",
        )
        room = await RoomRepository.create(
            session, code="ROOMROOMROOMROOM", creator_telegram_user_id=PARTNER,
            creator_name="P", theme="Acquaintance", level=1,
            content_type="questions", card_order=[0, 1],
        )
        await RoomRepository.seat_guest(session, room, ME, "Me")
        await CompatTestRepository.create(
            session, code="CMPTCMPTCMPTCMPT", creator_telegram_user_id=ME, creator_name="Me"
        )
        await Steps69Repository.create(
            session, code="S69GS69GS69GS69G", creator_telegram_user_id=ME,
            creator_name="Me", mode="solo", creator_piece="hearts",
        )
        await Steps69Repository.create(
            session, code="OTHEROTHEROTHER1", creator_telegram_user_id=PARTNER,
            creator_name="P", mode="solo", creator_piece="hearts",
        )
        certificate = await CertificateRepository.create(session, code="VECH-TEST-ERAS")
        await CertificateRepository.mark_as_used(session, certificate, ME)


async def test_erase_removes_the_person_and_what_they_sat_in(memory_db):
    await _populate()
    assert await user_has_access(ME) is True

    removed = await privacy.erase_user(ME)

    assert removed["user"] == 1
    assert removed["rooms"] == 1
    assert removed["compat_tests"] == 1
    assert removed["games"] == 1, "only the board the user sat in"
    assert removed["certificates_unlinked"] == 1
    assert removed["referrals_unlinked"] == 1

    assert {u.telegram_user_id for u in await _rows(User)} == {PARTNER, INVITED}
    assert await _rows(Subscription) == []
    assert await _rows(Payment) == []
    assert await _rows(Room) == []
    assert await _rows(CompatTest) == []
    assert [g.creator_telegram_user_id for g in await _rows(Steps69Game)] == [PARTNER]
    assert await user_has_access(ME) is False


async def test_a_redeemed_certificate_stays_spent_but_forgets_who(memory_db):
    await _populate()
    await privacy.erase_user(ME)
    [certificate] = await _rows(Certificate)
    assert certificate.is_used is True
    assert certificate.used_by_telegram_user_id is None


async def test_the_invited_keep_their_place_and_lose_the_link(memory_db):
    await _populate()
    async with get_db() as session:
        invited = await UserRepository.get_by_telegram_id(session, INVITED)
        assert invited.referred_by == ME
    await privacy.erase_user(ME)
    async with get_db() as session:
        invited = await UserRepository.get_by_telegram_id(session, INVITED)
        assert invited is not None
        assert invited.referred_by is None


async def test_erasing_a_stranger_removes_nothing(memory_db):
    await _populate()
    removed = await privacy.erase_user(999)
    assert removed["user"] == 0
    assert len(await _rows(User)) == 3


async def test_the_command_asks_before_it_deletes(mock_update, mock_context):
    with patch("vechnost_bot.privacy.erase_user", AsyncMock()) as erase:
        await privacy.delete_me_command(mock_update, mock_context)
    erase.assert_not_awaited()
    mock_update.message.reply_text.assert_awaited_once()
    text = mock_update.message.reply_text.await_args.args[0]
    assert text == get_text("privacy.ask", Language.RUSSIAN)
    markup = mock_update.message.reply_text.await_args.kwargs["reply_markup"]
    assert [b.callback_data for row in markup.inline_keyboard for b in row] == [
        privacy.CONFIRM, privacy.CANCEL
    ]


async def test_confirming_erases_and_says_so(mock_update, mock_callback_query, mock_context):
    mock_callback_query.data = privacy.CONFIRM
    with patch("vechnost_bot.privacy.erase_user", AsyncMock(return_value={"user": 1})) as erase:
        await privacy.delete_me_callback(mock_update, mock_context)
    erase.assert_awaited_once_with(mock_update.effective_user.id)
    shown = mock_callback_query.edit_message_text.await_args.args[0]
    assert shown == get_text("privacy.done", Language.RUSSIAN)


async def test_cancelling_erases_nothing(mock_update, mock_callback_query, mock_context):
    mock_callback_query.data = privacy.CANCEL
    with patch("vechnost_bot.privacy.erase_user", AsyncMock()) as erase:
        await privacy.delete_me_callback(mock_update, mock_context)
    erase.assert_not_awaited()
    shown = mock_callback_query.edit_message_text.await_args.args[0]
    assert shown == get_text("privacy.cancelled", Language.RUSSIAN)


async def test_a_tap_by_someone_else_is_ignored(mock_update, mock_callback_query, mock_context):
    mock_callback_query.data = privacy.CONFIRM
    mock_callback_query.from_user = MagicMock(id=mock_update.effective_user.id + 1)
    with patch("vechnost_bot.privacy.erase_user", AsyncMock()) as erase:
        await privacy.delete_me_callback(mock_update, mock_context)
    erase.assert_not_awaited()


def test_the_command_is_wired_ahead_of_the_catch_all():
    """A pattern handler after the catch-all is never reached."""
    from pathlib import Path

    source = Path("vechnost_bot/bot.py").read_text(encoding="utf-8")
    assert source.index("delete_me_callback, pattern=DELETE_ME_PATTERN") < source.index(
        "CallbackQueryHandler(handle_callback_query)"
    )
    assert 'BotCommand("delete_me"' in source
