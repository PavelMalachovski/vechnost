"""Whether the bot can write to someone is a fact about a chat, not a choice.

"bot can't initiate conversation with a user" is Telegram's answer for a
person who never opened a chat with the bot: a Tribute buyer, or a partner
who only ever opened an invite in the Mini App. It used to be read as a
block and opt them out of the daily card for good, and nothing - not a
/start days later - undid it. Now it marks `users.can_message` false, which
the daily card and a broadcast skip, and anything the person does in the
bot's chat marks it true again. An unsubscribe stays an unsubscribe.
"""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from telegram import Chat, Message, Update, WriteAccessAllowed
from telegram import User as TelegramUser
from telegram.error import Forbidden

import vechnost_bot.payments.database as database
from vechnost_bot import broadcast
from vechnost_bot.config import settings
from vechnost_bot.handlers import write_access_allowed
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.middleware import check_and_register_user
from vechnost_bot.payments.repositories import UserRepository

NEVER_STARTED = Forbidden("Forbidden: bot can't initiate conversation with a user")
BLOCKED = Forbidden("Forbidden: bot was blocked by the user")


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'reach.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def _user(user_id: int, *, can_message: bool = True, opt_out: bool = False) -> None:
    async with get_db() as session:
        await UserRepository.create_or_update(session, user_id, first_name=f"U{user_id}")
        await UserRepository.set_can_message(session, user_id, can_message)
        await UserRepository.set_daily_card_opt_out(session, user_id, opt_out)


async def _row(user_id: int):
    async with get_db() as session:
        return await UserRepository.get_by_telegram_id(session, user_id)


def _update_from(user_id: int) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = f"u{user_id}"
    update.effective_user.first_name = f"U{user_id}"
    update.effective_user.last_name = None
    update.effective_user.language_code = "ru"
    return update


# ---------------------------------------------------------------------------
# What a failed send means
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "unreachable", "opted_out"),
    [
        (NEVER_STARTED, True, False),
        (BLOCKED, False, True),
    ],
)
async def test_a_chat_never_opened_is_not_an_unsubscribe(error, unreachable, opted_out):
    send = AsyncMock(side_effect=error)
    with (
        patch.object(broadcast, "_cannot_message", new=AsyncMock()) as cannot,
        patch.object(broadcast, "_opt_out", new=AsyncMock()) as opt_out,
    ):
        assert await broadcast.deliver(send, 7) == broadcast.BLOCKED
    assert cannot.await_count == int(unreachable)
    assert opt_out.await_count == int(opted_out)
    assert send.await_count == 1  # neither is worth a retry


async def test_the_answer_is_written_on_the_row_and_nothing_else_changes(db):
    await _user(1)
    assert await broadcast.deliver(AsyncMock(side_effect=NEVER_STARTED), 1) == broadcast.BLOCKED
    row = await _row(1)
    assert (row.can_message, row.daily_card_opt_out) == (False, False)

    # Somebody the bot never wrote down gets no row out of it.
    await broadcast.deliver(AsyncMock(side_effect=NEVER_STARTED), 2)
    assert await _row(2) is None


# ---------------------------------------------------------------------------
# Who gets sent to
# ---------------------------------------------------------------------------


async def test_the_daily_card_and_a_broadcast_skip_whom_the_bot_cannot_reach(db):
    await _user(1)
    await _user(2, can_message=False)
    await _user(3, opt_out=True)
    async with get_db() as session:
        daily = [
            u.telegram_user_id for u in await UserRepository.get_daily_card_recipients(session)
        ]
        everyone = [u.telegram_user_id for u in await UserRepository.get_all(session)]
    assert daily == [1]
    # A broadcast still ignores the daily unsubscribe; it never tries a
    # chat that was never opened.
    assert everyone == [1, 3]


# ---------------------------------------------------------------------------
# Reachable again
# ---------------------------------------------------------------------------


async def test_writing_to_the_bot_makes_a_person_reachable_and_keeps_an_unsubscribe(db):
    await _user(1, can_message=False)
    await _user(2, can_message=False, opt_out=True)
    for user_id in (1, 2):
        await check_and_register_user(_update_from(user_id), None)

    assert (await _row(1)).can_message is True
    two = await _row(2)
    assert (two.can_message, two.daily_card_opt_out) == (True, True)
    async with get_db() as session:
        daily = [
            u.telegram_user_id for u in await UserRepository.get_daily_card_recipients(session)
        ]
    assert daily == [1]


async def test_allowing_the_bot_to_write_from_the_app_marks_them_reachable(db):
    await _user(1, can_message=False)
    await write_access_allowed(_update_from(1), None)
    assert (await _row(1)).can_message is True

    # And somebody the bot had never seen gets a row it can use.
    await write_access_allowed(_update_from(2), None)
    assert (await _row(2)).can_message is True


async def test_a_purchase_says_nothing_about_a_chat(db):
    """The payment webhook registers the buyer too; that must not undo what
    a failed send found out."""
    await _user(1, can_message=False)
    async with get_db() as session:
        await UserRepository.create_or_update(session, 1, first_name="Buyer")
    assert (await _row(1)).can_message is False


def test_the_service_message_reaches_its_handler_even_from_an_admin():
    """The admin's broadcast capture takes every private message from an
    admin that is not a command; an admin allowing the bot to write would
    have been read as a draft nobody asked for."""
    from vechnost_bot.bot import create_application

    with patch.object(settings, "admin_ids", "111"):
        app = create_application()
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=111, type=Chat.PRIVATE),
        from_user=TelegramUser(id=111, first_name="Admin", is_bot=False),
        write_access_allowed=WriteAccessAllowed(from_request=True),
    )
    update = Update(update_id=1, message=message)
    first = next(h for h in app.handlers[0] if h.check_update(update))
    assert first.callback is write_access_allowed


# ---------------------------------------------------------------------------
# The column on a deployed database
# ---------------------------------------------------------------------------


async def test_a_deployed_table_gets_the_column_with_everyone_reachable(db):
    from sqlalchemy import text

    await _user(1)
    async with database._engine().begin() as conn:
        await conn.execute(text("ALTER TABLE users DROP COLUMN can_message"))
    await database.create_tables()
    await database.create_tables()  # a second start changes nothing

    assert (await _row(1)).can_message is True
    await database.close_db()
