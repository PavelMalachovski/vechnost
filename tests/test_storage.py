"""Where a chat's session lives: memory by default, Redis only when asked.

The storage used to ignore REDIS_URL (localhost was hard-coded), start a
`redis-server` of its own - synchronously, twice, on the bot's event loop -
and keep sessions in memory with no expiry and no bound when that failed,
which on Railway it always did. These hold the replacement to its word.
"""

import asyncio
import json
import subprocess
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vechnost_bot import storage
from vechnost_bot.config import settings
from vechnost_bot.models import ContentType, Language, SessionState, Theme
from vechnost_bot.storage import (
    MemorySessionStore,
    RedisSessionStore,
    configured_store,
    delete_session,
    get_session,
    save_session,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ---------------------------------------------------------------------------
# Choosing the store
# ---------------------------------------------------------------------------


def test_without_redis_url_sessions_stay_in_memory():
    with patch.object(settings, "redis_url", None):
        assert isinstance(configured_store(), MemorySessionStore)


def test_redis_url_is_the_redis_that_is_used():
    """The URL used to be ignored for a hard-coded localhost:6379."""
    with patch.object(settings, "redis_url", "redis://cache.internal:6380/3"):
        store = configured_store()

    assert isinstance(store, RedisSessionStore)
    kwargs = store._client.connection_pool.connection_kwargs
    assert kwargs["host"] == "cache.internal"
    assert kwargs["port"] == 6380
    assert kwargs["db"] == 3
    # Every call is bounded: a Redis that has gone away costs a tap seconds.
    assert kwargs["socket_timeout"] == storage.REDIS_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == storage.REDIS_TIMEOUT_SECONDS


def test_redis_db_chooses_the_database_a_url_leaves_open():
    """REDIS_DB applies to a URL without a database, and only to one."""
    from vechnost_bot.config import Settings

    env = {"REDIS_URL": "redis://cache.internal:6379", "REDIS_DB": "4"}
    with patch.dict("os.environ", env):
        fresh = Settings()
    with (
        patch.object(settings, "redis_url", fresh.redis_url),
        patch.object(settings, "redis_db", fresh.redis_db),
    ):
        assert configured_store()._client.connection_pool.connection_kwargs["db"] == 4

    with (
        patch.object(settings, "redis_url", "redis://cache.internal:6379/2"),
        patch.object(settings, "redis_db", 4),
    ):
        assert configured_store()._client.connection_pool.connection_kwargs["db"] == 2


def test_a_blank_redis_url_means_no_redis():
    from vechnost_bot.config import Settings

    with patch.dict("os.environ", {"REDIS_URL": ""}):
        assert Settings().redis_url is None


async def test_nothing_starts_a_redis_server():
    """No `redis-server` is launched, whatever is or is not configured.

    The old storage ran `redis-server` and `redis-cli ping` through
    `subprocess` with `time.sleep` between attempts, on the event loop, on
    the first touch of a session: six seconds on a machine without the
    binary, up to a minute and a half on one where it would not start.
    """
    for url in (None, "redis://127.0.0.1:1/0"):
        with (
            patch.object(settings, "redis_url", url),
            patch.object(storage, "_store", None),
            patch.object(subprocess, "Popen", side_effect=AssertionError("spawned")),
            patch.object(subprocess, "run", side_effect=AssertionError("ran")),
        ):
            store = storage.session_store()
            if url is None:
                await get_session(1)
            await store.close()


async def test_a_redis_that_is_not_there_is_an_error_not_a_fallback():
    """Honest failure: no silent switch to a second store, no long hang.

    Falling back to memory would split one chat's session across two
    stores; the old fallback was also unreachable, because the Redis store
    swallowed every error itself and answered None.
    """
    from redis.exceptions import ConnectionError as RedisConnectionError

    # Nothing listens on port 1, so the connection is refused at once.
    store = RedisSessionStore("redis://127.0.0.1:1/0", ttl=60, timeout=0.5)
    try:
        started = time.monotonic()
        with pytest.raises(RedisConnectionError):
            await store.get_session(1)
        with pytest.raises(RedisConnectionError):
            await store.save_session(1, SessionState())
        assert time.monotonic() - started < 5
    finally:
        await store.close()


# ---------------------------------------------------------------------------
# The memory store
# ---------------------------------------------------------------------------


async def test_a_session_is_forgotten_ttl_seconds_after_its_last_save():
    clock = FakeClock()
    store = MemorySessionStore(ttl=60, clock=clock)
    await store.save_session(1, SessionState(theme=Theme.SEX))

    clock.now += 59
    assert (await store.get_session(1)).theme is Theme.SEX

    # Saving again restarts the clock.
    await store.save_session(1, SessionState(theme=Theme.PROVOCATION))
    clock.now += 59
    assert (await store.get_session(1)).theme is Theme.PROVOCATION

    clock.now += 1
    assert await store.get_session(1) is None
    assert len(store) == 0


async def test_expired_sessions_do_not_pile_up():
    """Nobody has to read an expired session for it to go: the dictionary
    used to grow for as long as the process lived."""
    clock = FakeClock()
    store = MemorySessionStore(ttl=60, clock=clock)
    for chat_id in range(100):
        await store.save_session(chat_id, SessionState())

    clock.now += 61
    await store.save_session(1000, SessionState())

    assert len(store) == 1


async def test_the_store_is_bounded_and_drops_the_least_recently_saved():
    store = MemorySessionStore(ttl=3600, max_sessions=3)
    for chat_id in (1, 2, 3):
        await store.save_session(chat_id, SessionState())
    await store.save_session(1, SessionState(level=2))  # 1 is fresh again

    await store.save_session(4, SessionState())

    assert len(store) == 3
    assert await store.get_session(2) is None
    assert (await store.get_session(1)).level == 2
    assert await store.get_session(3) is not None
    assert await store.get_session(4) is not None


async def test_a_read_hands_out_a_copy_as_redis_does():
    """Memory behaves like the store that serializes, so code that only
    worked because two reads were one object fails in the tests too."""
    store = MemorySessionStore(ttl=60)
    await store.save_session(1, SessionState(theme=Theme.SEX, drawn_cards={"a"}))

    first = await store.get_session(1)
    first.theme = None
    first.drawn_cards.add("b")

    again = await store.get_session(1)
    assert again is not first
    assert again.theme is Theme.SEX
    assert again.drawn_cards == {"a"}


async def test_a_stored_retired_language_comes_back_russian():
    store = MemorySessionStore(ttl=60)
    store._rows[7] = (
        time.monotonic() + 60,
        json.dumps(
            {
                "theme": "Acquaintance",
                "level": 2,
                "content_type": "questions",
                "drawn_cards": ["x"],
                "is_nsfw_confirmed": True,
                "language": "en",
            }
        ),
    )

    session = await store.get_session(7)

    assert session is not None
    assert session.language is Language.RUSSIAN
    assert session.theme is Theme.ACQUAINTANCE
    assert session.content_type is ContentType.QUESTIONS
    assert session.is_nsfw_confirmed is True


async def test_an_unreadable_session_is_a_fresh_start_not_an_error():
    store = MemorySessionStore(ttl=60)
    store._rows[7] = (time.monotonic() + 60, "{not json")
    assert await store.get_session(7) is None
    assert len(store) == 0


# ---------------------------------------------------------------------------
# The facade the handlers use
# ---------------------------------------------------------------------------


async def test_an_unknown_chat_gets_a_fresh_session_and_nothing_is_written():
    session = await get_session(4242)

    assert session == SessionState()
    assert len(storage.session_store()) == 0


async def test_save_get_delete_round_trip():
    await save_session(5, SessionState(theme=Theme.FOR_COUPLES, level=3))
    assert (await get_session(5)).level == 3

    await delete_session(5)
    assert await get_session(5) == SessionState()
    # Removed, not tombstoned: nothing is left holding the chat.
    assert len(storage.session_store()) == 0


async def test_a_session_read_does_not_hold_the_event_loop():
    """The first touch of a session used to stall every other update for
    seconds while a Redis server was started; now it is a dictionary read."""
    beats: list[float] = []

    async def heartbeat() -> None:
        while True:
            beats.append(time.monotonic())
            await asyncio.sleep(0.01)

    ticker = asyncio.create_task(heartbeat())
    try:
        await asyncio.sleep(0.02)
        with patch.object(storage, "_store", None), patch.object(settings, "redis_url", None):
            await get_session(1)
            await save_session(1, SessionState())
        await asyncio.sleep(0.02)
    finally:
        ticker.cancel()

    gaps = [b - a for a, b in zip(beats, beats[1:], strict=False)]
    assert max(gaps) < 0.5


# ---------------------------------------------------------------------------
# «Сбросить игру» over a store that serializes
# ---------------------------------------------------------------------------


class _SerializingStore:
    """Hands out a fresh copy on every read, the way Redis does.

    The in-memory store returned the very object it was given, so two reads
    of one chat were one object and a change made through either showed up
    in both. Anything that serializes breaks that, and code that relied on
    it only works in memory.
    """

    kind = "fake"

    def __init__(self) -> None:
        self.rows: dict[int, str] = {}

    async def get_session(self, chat_id: int) -> SessionState | None:
        raw = self.rows.get(chat_id)
        return SessionState.model_validate_json(raw) if raw is not None else None

    async def save_session(self, chat_id: int, session: SessionState) -> None:
        self.rows[chat_id] = session.model_dump_json()

    async def delete_session(self, chat_id: int) -> None:
        self.rows.pop(chat_id, None)

    async def close(self) -> None:
        self.rows.clear()


@pytest.mark.parametrize(
    "make_store",
    [
        _SerializingStore,
        lambda: MemorySessionStore(ttl=60),
    ],
    ids=["serializing-fake", "memory"],
)
async def test_reset_sticks_when_the_store_serializes_the_session(make_store):
    """«Сбросить игру» must reset what is saved, not a copy of it.

    The registry reads the session, runs the handler and saves the session
    back. The reset handler used to reset a *second* copy through
    `storage.reset_session` and save that, after which the registry saved
    its own, untouched copy over it - so with Redis behind the bot the game
    announced a reset and kept the theme, the level and the 18+ consent.
    """
    from vechnost_bot.callback_handlers import CallbackHandlerRegistry

    store = make_store()
    chat_id = 4242
    await store.save_session(
        chat_id,
        SessionState(
            theme=Theme.SEX,
            level=2,
            is_nsfw_confirmed=True,
        ),
    )

    query = MagicMock()
    query.message.chat.id = chat_id
    query.message.photo = ()
    query.edit_message_text = AsyncMock()

    with patch.object(storage, "_store", store):
        await CallbackHandlerRegistry().handle_callback(query, "reset_confirm")

    saved = await store.get_session(chat_id)
    assert saved is not None
    assert saved.theme is None
    assert saved.level is None
    assert saved.is_nsfw_confirmed is False
