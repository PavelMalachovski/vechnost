"""The local SQLite file keeps the promises PostgreSQL's row locks keep.

Local development and most of this suite run on a SQLite file. It used to be
opened through `StaticPool`, one connection shared by every request, so two
requests at once were one transaction with their statements interleaved: a
crowd opening one invite seated nobody and a double tap turned six cards
(audit B-13). Now every session has a connection of its own and begins
IMMEDIATE, because SQLite ignores `FOR UPDATE`: the second read-modify-write
waits for the first to commit and then reads what it wrote.

An in-memory database keeps the single shared connection: it exists only
inside that connection.
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy.pool import NullPool, StaticPool

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import RoomRepository

CODE = "POOLPOOLPOOLPOOL"


@pytest.fixture
def db_at():
    """Point the app at a database URL of the test's choosing."""

    def use(url):
        stack = [
            patch.object(settings, "database_url", url),
            patch.object(database, "engine", None),
            patch.object(database, "async_session_maker", None),
            patch.object(database, "_tables_created", False),
        ]
        for p in stack:
            p.start()
        used.extend(stack)

    used = []
    yield use
    for p in reversed(used):
        p.stop()


def test_a_sqlite_file_gets_a_connection_per_session(db_at, tmp_path):
    db_at(f"sqlite:///{tmp_path / 'pool.db'}")
    database.init_db()
    assert isinstance(database.engine.sync_engine.pool, NullPool)


@pytest.mark.parametrize("url", [
    "sqlite:///:memory:",
    "sqlite+aiosqlite:///:memory:",
    "sqlite+aiosqlite:///file:shared?mode=memory&cache=shared&uri=true",
])
def test_an_in_memory_database_keeps_its_one_connection(db_at, url):
    db_at(url)
    database.init_db()
    assert isinstance(database.engine.sync_engine.pool, StaticPool)


async def test_read_modify_writes_on_a_sqlite_file_take_turns(db_at, tmp_path):
    """Five taps land together; each reads the row, then writes it.

    With one shared connection they all read card 0 and all wrote card 1;
    with a connection each but the driver's own BEGIN, the reads still
    happened outside any transaction and four taps were lost.
    """
    db_at(f"sqlite:///{tmp_path / 'taps.db'}")
    async with get_db() as session:
        await RoomRepository.create(
            session, code=CODE, creator_telegram_user_id=1, creator_name="A",
            theme="Acquaintance", level=1, content_type="questions",
            card_order=list(range(10)),
        )

    async def tap() -> None:
        async with get_db() as session:
            room = await RoomRepository.get_by_code(session, CODE, for_update=True)
            seen = room.idx
            await asyncio.sleep(0.02)  # every other tap arrives in here
            room.idx = seen + 1

    await asyncio.gather(*(tap() for _ in range(5)))

    async with get_db() as session:
        room = await RoomRepository.get_by_code(session, CODE)
        assert room.idx == 5
