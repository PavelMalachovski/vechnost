"""What gets deleted, and what deliberately does not."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import (
    CompatTestRepository,
    RoomRepository,
    Steps69Repository,
)
from vechnost_bot.retention import ABANDONED_KEEP, ROOM_KEEP, sweep


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'ret.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def _room(code, age):
    async with get_db() as session:
        room = await RoomRepository.create(
            session, code=code, creator_telegram_user_id=1, creator_name="A",
            theme="Acquaintance", level=1, content_type="questions", card_order=[0, 1],
        )
        room.updated_at = datetime.utcnow() - age


async def _compat(code, age, finished=False):
    async with get_db() as session:
        test = await CompatTestRepository.create(
            session, code=code, creator_telegram_user_id=1, creator_name="A",
        )
        test.updated_at = datetime.utcnow() - age
        if finished:
            test.finished_at = datetime.utcnow() - age


async def _game(code, age, finished=False):
    async with get_db() as session:
        game = await Steps69Repository.create(
            session, code=code, creator_telegram_user_id=1, creator_name="A",
            mode="duo", creator_piece="hearts",
        )
        game.updated_at = datetime.utcnow() - age
        game.finished = finished


async def _alive(repo, code):
    async with get_db() as session:
        return await repo.get_by_code(session, code) is not None


# ---------------------------------------------------------------------------
# What goes
# ---------------------------------------------------------------------------

async def test_a_room_past_its_ttl_is_deleted(db):
    """It already answers 410 on read; the row was simply never removed."""
    await _room("OLDROOM1", ROOM_KEEP + timedelta(hours=1))
    assert (await sweep())["rooms"] == 1
    assert not await _alive(RoomRepository, "OLDROOM1")


async def test_an_abandoned_compatibility_test_is_deleted(db):
    await _compat("OLDCMP01", ABANDONED_KEEP + timedelta(days=1))
    assert (await sweep())["compat_tests"] == 1
    assert not await _alive(CompatTestRepository, "OLDCMP01")


async def test_an_abandoned_board_is_deleted(db):
    await _game("OLDGAME1", ABANDONED_KEEP + timedelta(days=1))
    assert (await sweep())["games"] == 1
    assert not await _alive(Steps69Repository, "OLDGAME1")


# ---------------------------------------------------------------------------
# What stays, which matters more
# ---------------------------------------------------------------------------

async def test_a_finished_compatibility_test_is_kept_however_old(db):
    """Eighty questions produced that result and it has no TTL on purpose:
    the pair are meant to be able to re-read it months later."""
    await _compat("DONECMP1", ABANDONED_KEEP * 4, finished=True)
    assert (await sweep())["compat_tests"] == 0
    assert await _alive(CompatTestRepository, "DONECMP1")


async def test_a_finished_game_is_kept_however_old(db):
    await _game("DONEGAM1", ABANDONED_KEEP * 4, finished=True)
    assert (await sweep())["games"] == 0
    assert await _alive(Steps69Repository, "DONEGAM1")


async def test_a_pair_who_stopped_last_month_keep_their_board(db):
    """No TTL is the feature: a board left at cell 45 is still at cell 45."""
    await _game("PAUSED01", timedelta(days=30))
    assert (await sweep())["games"] == 0
    assert await _alive(Steps69Repository, "PAUSED01")


async def test_a_test_half_answered_last_week_is_kept(db):
    await _compat("HALFCMP1", timedelta(days=7))
    assert (await sweep())["compat_tests"] == 0
    assert await _alive(CompatTestRepository, "HALFCMP1")


async def test_a_room_being_played_right_now_is_kept(db):
    await _room("LIVEROOM", timedelta(minutes=5))
    assert (await sweep())["rooms"] == 0
    assert await _alive(RoomRepository, "LIVEROOM")


async def test_a_sweep_with_nothing_to_do_deletes_nothing(db):
    await _room("LIVEROOM", timedelta(minutes=1))
    await _compat("LIVECMP1", timedelta(minutes=1))
    await _game("LIVEGAM1", timedelta(minutes=1))
    assert await sweep() == {"rooms": 0, "compat_tests": 0, "games": 0}


async def test_one_sweep_clears_all_three_kinds(db):
    await _room("OLDROOM1", ROOM_KEEP * 2)
    await _compat("OLDCMP01", ABANDONED_KEEP * 2)
    await _game("OLDGAME1", ABANDONED_KEEP * 2)
    assert await sweep() == {"rooms": 1, "compat_tests": 1, "games": 1}


async def test_the_room_window_is_wider_than_the_ttl(db):
    """Slack for a clock skew or a job that did not run, not a second chance
    at reading an expired room."""
    from vechnost_bot.payments.rooms import ROOM_TTL

    assert ROOM_KEEP > ROOM_TTL
