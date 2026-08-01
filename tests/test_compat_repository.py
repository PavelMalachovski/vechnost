"""Tests for compatibility-test persistence."""

import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vechnost_bot.payments.models import Base, CompatTest  # noqa: F401
from vechnost_bot.payments.repositories import CompatTestRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_create_and_fetch_by_code(session):
    created = await CompatTestRepository.create(
        session, code="ABC123", creator_telegram_user_id=1, creator_name="A"
    )
    assert created.creator_answers == [None] * 40
    assert created.guest_answers == [None] * 40
    assert created.pair_key is None
    assert created.finished_at is None

    found = await CompatTestRepository.get_by_code(session, "ABC123")
    assert found is not None and found.id == created.id


async def test_unknown_code_is_none(session):
    assert await CompatTestRepository.get_by_code(session, "NOPE99") is None


async def test_latest_completed_for_returns_only_finished_sessions(session):
    from datetime import datetime

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
    assert (await CompatTestRepository.latest_completed_for(session, 8)).code == "AAA111"


async def test_delete_superseded_removes_other_rows_for_the_same_pair(session):
    from datetime import datetime

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

    removed = await CompatTestRepository.delete_superseded(session, "1:2", keep_id=new.id)
    assert removed == 1
    assert await CompatTestRepository.get_by_code(session, "OLD111") is None
    assert await CompatTestRepository.get_by_code(session, "NEW111") is not None
    assert await CompatTestRepository.get_by_code(session, "OTH111") is not None
