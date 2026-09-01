"""The daily-card opt-out must stick even for a user the bot never wrote down.

`set_daily_card_opt_out` used to be a silent no-op when the user row was
missing, and the button confirmed the unsubscribe anyway — the worst failure
mode an unsubscribe can have.
"""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import UserRepository


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'optout.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def test_opt_out_creates_the_missing_row(db):
    async with get_db() as session:
        await UserRepository.set_daily_card_opt_out(session, 555001, True)

    async with get_db() as session:
        user = await UserRepository.get_by_telegram_id(session, 555001)
        assert user is not None
        assert user.daily_card_opt_out is True


async def test_opt_out_flips_an_existing_row(db):
    async with get_db() as session:
        await UserRepository.create_or_update(session, telegram_user_id=555002)
    async with get_db() as session:
        await UserRepository.set_daily_card_opt_out(session, 555002, True)
    async with get_db() as session:
        user = await UserRepository.get_by_telegram_id(session, 555002)
        assert user.daily_card_opt_out is True

    # And back on: a resubscribe from the same button.
    async with get_db() as session:
        await UserRepository.set_daily_card_opt_out(session, 555002, False)
    async with get_db() as session:
        user = await UserRepository.get_by_telegram_id(session, 555002)
        assert user.daily_card_opt_out is False


async def test_an_opted_out_ghost_row_is_not_a_recipient(db):
    """The row minted by an opt-out must not add its user to the push list."""
    async with get_db() as session:
        await UserRepository.set_daily_card_opt_out(session, 555003, True)
    async with get_db() as session:
        recipients = await UserRepository.get_daily_card_recipients(session)
        assert 555003 not in {u.telegram_user_id for u in recipients}
