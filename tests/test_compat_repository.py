"""Tests for compatibility-test persistence.

These are plain synchronous test functions that call asyncio.run() around an
inner coroutine, following tests/test_rooms.py::test_expired_room_410. This
repo's tests/conftest.py defines a session-scoped event_loop fixture that
conflicts with pytest-asyncio's function-scoped default, so bare async
fixtures / async test functions error on collection with ScopeMismatch.
Nothing here is defined at module scope as an async fixture.
"""

import asyncio
import os
from datetime import datetime

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vechnost_bot.payments.models import Base
from vechnost_bot.payments.repositories import CompatTestRepository


async def _make_session():
    """A fresh in-memory sqlite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, maker()


def test_create_and_fetch_by_code():
    async def scenario():
        engine, session = await _make_session()
        try:
            created = await CompatTestRepository.create(
                session, code="ABC123", creator_telegram_user_id=1, creator_name="A"
            )
            assert created.creator_answers == [None] * 40
            assert created.guest_answers == [None] * 40
            assert created.pair_key is None
            assert created.finished_at is None

            found = await CompatTestRepository.get_by_code(session, "ABC123")
            assert found is not None and found.id == created.id
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_unknown_code_is_none():
    async def scenario():
        engine, session = await _make_session()
        try:
            assert await CompatTestRepository.get_by_code(session, "NOPE99") is None
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_latest_completed_for_returns_only_finished_sessions():
    async def scenario():
        engine, session = await _make_session()
        try:
            unfinished = await CompatTestRepository.create(
                session, code="AAA111", creator_telegram_user_id=7, creator_name="A"
            )
            unfinished.guest_telegram_user_id = 8
            await session.flush()
            assert await CompatTestRepository.latest_completed_for(session, 7) is None

            unfinished.finished_at = datetime.utcnow()
            await session.flush()
            found = await CompatTestRepository.latest_completed_for(session, 7)
            assert found is not None and found.code == "AAA111"
            # The guest can read it too.
            guest_found = await CompatTestRepository.latest_completed_for(session, 8)
            assert guest_found.code == "AAA111"
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_delete_superseded_removes_other_rows_for_the_same_pair():
    async def scenario():
        engine, session = await _make_session()
        try:
            old = await CompatTestRepository.create(
                session, code="OLD111", creator_telegram_user_id=1, creator_name="A"
            )
            old.guest_telegram_user_id = 2
            old.pair_key = "1:2"
            old.finished_at = datetime.utcnow()

            other_pair = await CompatTestRepository.create(
                session, code="OTH111", creator_telegram_user_id=1, creator_name="A"
            )
            other_pair.guest_telegram_user_id = 3
            other_pair.pair_key = "1:3"
            other_pair.finished_at = datetime.utcnow()

            new = await CompatTestRepository.create(
                session, code="NEW111", creator_telegram_user_id=2, creator_name="B"
            )
            new.guest_telegram_user_id = 1
            new.pair_key = "1:2"
            new.finished_at = datetime.utcnow()
            await session.flush()

            removed = await CompatTestRepository.delete_superseded(
                session, "1:2", keep_id=new.id
            )
            assert removed == 1
            assert await CompatTestRepository.get_by_code(session, "OLD111") is None
            assert await CompatTestRepository.get_by_code(session, "NEW111") is not None
            assert await CompatTestRepository.get_by_code(session, "OTH111") is not None
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_delete_superseded_with_null_pair_key_is_a_no_op():
    """
    A null pair_key must never become a delete-everything-unpaired footgun.

    SQLAlchemy compiles `Column == None` to `IS NULL`, which every unpaired
    session across every user matches — not "no session". Without the
    early-return guard in delete_superseded, this call would delete both
    unpaired sessions below (and any other unpaired session in the table).
    """

    async def scenario():
        engine, session = await _make_session()
        try:
            unpaired_a = await CompatTestRepository.create(
                session, code="NUL111", creator_telegram_user_id=1, creator_name="A"
            )
            await CompatTestRepository.create(
                session, code="NUL222", creator_telegram_user_id=2, creator_name="B"
            )
            paired = await CompatTestRepository.create(
                session, code="PAI111", creator_telegram_user_id=3, creator_name="C"
            )
            paired.guest_telegram_user_id = 4
            paired.pair_key = "3:4"
            paired.finished_at = datetime.utcnow()
            await session.flush()

            removed = await CompatTestRepository.delete_superseded(
                session, None, keep_id=unpaired_a.id
            )
            assert removed == 0
            assert await CompatTestRepository.get_by_code(session, "NUL111") is not None
            assert await CompatTestRepository.get_by_code(session, "NUL222") is not None
            assert await CompatTestRepository.get_by_code(session, "PAI111") is not None
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(scenario())
