"""The nudge for a game left standing on the board."""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from telegram.error import Forbidden

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import Steps69Repository
from vechnost_bot.steps69_notify import (
    GIVE_UP_AFTER,
    IDLE_BEFORE_NUDGE,
    nudge_stalled_games,
)


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'nudge.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def _game(code, *, position, idle, turns=4, finished=False, notified=None):
    """A game in whatever state the test needs, aged by hand."""
    async with get_db() as session:
        game = await Steps69Repository.create(
            session, code=code, creator_telegram_user_id=11,
            creator_name="A", mode="duo",
        )
        game.guest_telegram_user_id = 22
        game.guest_name = "B"
        game.position = position
        game.turns = turns
        game.finished = finished
        game.resume_notified_at = notified
        game.updated_at = datetime.utcnow() - idle
    return code


def _bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


async def test_a_stalled_game_nudges_both_partners(db):
    await _game("AAAAAA", position=45, idle=IDLE_BEFORE_NUDGE + timedelta(hours=2))
    bot = _bot()

    assert await nudge_stalled_games(bot) == 1
    assert bot.send_message.await_count == 2
    assert {c.kwargs["chat_id"] for c in bot.send_message.await_args_list} == {11, 22}
    assert "45" in bot.send_message.await_args_list[0].kwargs["text"]


async def test_a_game_in_play_is_left_alone(db):
    """A pair rolling right now must not be told to come back."""
    await _game("BBBBBB", position=12, idle=timedelta(minutes=5))
    bot = _bot()
    assert await nudge_stalled_games(bot) == 0
    bot.send_message.assert_not_awaited()


async def test_a_finished_game_is_not_nudged(db):
    await _game("CCCCCC", position=69, idle=IDLE_BEFORE_NUDGE * 2, finished=True)
    bot = _bot()
    assert await nudge_stalled_games(bot) == 0


async def test_a_game_that_was_never_rolled_is_not_stalled(db):
    """Nobody abandoned a board they never touched; they opened the screen."""
    await _game("DDDDDD", position=1, idle=IDLE_BEFORE_NUDGE * 2, turns=0)
    bot = _bot()
    assert await nudge_stalled_games(bot) == 0


async def test_a_long_abandoned_game_is_let_go(db):
    """Past the cut-off a message reads as the app trawling their history."""
    await _game("EEEEEE", position=30, idle=GIVE_UP_AFTER + timedelta(days=1))
    bot = _bot()
    assert await nudge_stalled_games(bot) == 0


async def test_a_game_is_only_nudged_once(db):
    await _game("FFFFFF", position=45, idle=IDLE_BEFORE_NUDGE * 2)
    bot = _bot()

    assert await nudge_stalled_games(bot) == 1
    bot.send_message.reset_mock()
    assert await nudge_stalled_games(bot) == 0
    bot.send_message.assert_not_awaited()


async def test_one_blocked_partner_does_not_cost_the_other_their_nudge(db):
    await _game("GGGGGG", position=45, idle=IDLE_BEFORE_NUDGE * 2)
    bot = _bot()
    bot.send_message.side_effect = [Forbidden("blocked"), None]

    assert await nudge_stalled_games(bot) == 1
    assert bot.send_message.await_count == 2


async def test_a_game_nobody_could_be_reached_about_is_not_counted(db):
    await _game("HHHHHH", position=45, idle=IDLE_BEFORE_NUDGE * 2)
    bot = _bot()
    bot.send_message.side_effect = Forbidden("blocked")

    assert await nudge_stalled_games(bot) == 0


async def test_rolling_again_makes_a_game_eligible_for_a_later_nudge(db):
    """The flag records "we nudged about this stall", not "this game is
    spent": a pair who come back, play on and stall again deserve another."""
    await _game(
        "IIIIII", position=45, idle=IDLE_BEFORE_NUDGE * 2,
        notified=datetime.utcnow() - timedelta(days=1),
    )
    bot = _bot()
    assert await nudge_stalled_games(bot) == 0

    async with get_db() as session:
        game = await Steps69Repository.get_by_code(session, "IIIIII")
        game.resume_notified_at = None          # what /roll does
        game.updated_at = datetime.utcnow() - IDLE_BEFORE_NUDGE * 2

    assert await nudge_stalled_games(bot) == 1
