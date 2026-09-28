"""Sessions in a real Redis, the store the bot uses when REDIS_URL is set."""

import asyncio
import os
from unittest.mock import patch

import pytest
import pytest_asyncio

from vechnost_bot import storage
from vechnost_bot.config import settings
from vechnost_bot.models import ContentType, Language, SessionState, Theme
from vechnost_bot.storage import RedisSessionStore

# Everything here talks to a real server on localhost:6379. The marker is what
# lets conftest skip the file when there is none, and what keeps the autouse
# in-memory fixture off these tests.
pytestmark = pytest.mark.redis


def _test_db() -> int:
    """A database of this worker's own, so parallel runs cannot collide.

    Redis ships sixteen numbered databases and the app uses 0, so the tests
    count down from 15. Under `-n auto` each xdist worker gets its own, which
    is what makes flushing safe: without this, two workers would flush each
    other's keys mid-test and the failure would land on whichever was slower.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    index = int(worker[2:]) if worker.startswith("gw") and worker[2:].isdigit() else 0
    return 15 - min(index, 14)


def _url() -> str:
    return f"redis://localhost:6379/{_test_db()}"


@pytest_asyncio.fixture
async def store():
    """A store on this worker's database, empty at both ends."""
    store = RedisSessionStore(_url(), ttl=60)
    await store._client.flushdb()
    try:
        yield store
    finally:
        await store._client.flushdb()
        await store.close()


async def test_a_session_round_trips(store):
    session = SessionState(
        language=Language.RUSSIAN,
        theme=Theme.SEX,
        level=None,
        content_type=ContentType.TASKS,
        drawn_cards={"one", "two"},
        is_nsfw_confirmed=True,
    )
    await store.save_session(12345, session)

    back = await store.get_session(12345)
    assert back == session
    assert back is not session

    await store.delete_session(12345)
    assert await store.get_session(12345) is None


async def test_a_session_expires_after_the_ttl(store):
    await store.save_session(1, SessionState())
    ttl = await store._client.ttl("session:1")
    assert 0 < ttl <= 60


async def test_redis_url_decides_where_sessions_go(store):
    """The facade, configured from REDIS_URL alone, writes to that database.

    The old storage connected to localhost:6379 database 0 whatever the URL
    named, so a session written through it never reached this one.
    """
    with (
        patch.object(settings, "redis_url", _url()),
        patch.object(storage, "_store", None),
    ):
        await storage.save_session(777, SessionState(theme=Theme.PROVOCATION))
        assert storage.session_store().kind == "redis"
        await storage.close_session_store()

    assert (await store.get_session(777)).theme is Theme.PROVOCATION


async def test_many_chats_at_once_queue_for_the_pool_rather_than_fail(store):
    """More concurrent chats than the pool has connections.

    A plain pool raises "Too many connections" past its size, which lost
    sessions under a burst; the blocking pool makes the extra callers wait.
    """
    small = RedisSessionStore(_url(), ttl=60, max_connections=2)
    try:
        chat_ids = list(range(1000, 1040))
        await asyncio.gather(
            *(
                small.save_session(chat_id, SessionState(level=chat_id % 3 + 1))
                for chat_id in chat_ids
            )
        )
        found = await asyncio.gather(*(small.get_session(c) for c in chat_ids))
        assert all(session is not None for session in found)
    finally:
        await small.close()
