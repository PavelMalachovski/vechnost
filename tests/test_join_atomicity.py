"""The second seat is taken by one conditional UPDATE, never read-then-write.

Rooms, compatibility tests and boards all used to check
`guest_telegram_user_id is None` and then assign it. Two partners opening
the same link at the same moment both saw an empty seat, both wrote
themselves into it, and the last writer displaced the first without anyone
being told. The WHERE clause now carries the check, so the database seats
exactly one of them and the other is told the room is full.
"""

from unittest.mock import patch

import pytest

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import (
    CompatTestRepository,
    RoomRepository,
    Steps69Repository,
)


@pytest.fixture
def memory_db():
    with (
        patch.object(settings, "database_url", "sqlite+aiosqlite:///:memory:"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield


async def test_a_room_seats_one_guest(memory_db):
    async with get_db() as session:
        room = await RoomRepository.create(
            session, code="ROOMROOMROOMROOM", creator_telegram_user_id=1,
            creator_name="A", theme="Acquaintance", level=1,
            content_type="questions", card_order=[0, 1, 2],
        )
        assert await RoomRepository.seat_guest(session, room, 2, "Bob") is True
        assert await RoomRepository.seat_guest(session, room, 3, "Eve") is False
        assert room.guest_telegram_user_id == 2
        assert room.guest_name == "Bob"


async def test_a_compat_test_seats_one_guest_and_keeps_the_pair_key(memory_db):
    async with get_db() as session:
        test = await CompatTestRepository.create(
            session, code="CMPTCMPTCMPTCMPT", creator_telegram_user_id=10, creator_name="A"
        )
        assert await CompatTestRepository.seat_guest(session, test, 7, "Bob") is True
        assert await CompatTestRepository.seat_guest(session, test, 8, "Eve") is False
        assert test.guest_telegram_user_id == 7
        assert test.pair_key == "7:10"


async def test_a_board_seats_one_guest_with_their_suit(memory_db):
    async with get_db() as session:
        game = await Steps69Repository.create(
            session, code="S69GS69GS69GS69G", creator_telegram_user_id=1,
            creator_name="A", mode="duo", creator_piece="hearts",
        )
        assert await Steps69Repository.seat_guest(session, game, 2, "Bob", "spades") is True
        assert await Steps69Repository.seat_guest(session, game, 3, "Eve", "clubs") is False
        assert game.guest_telegram_user_id == 2
        assert game.guest_piece == "spades"
