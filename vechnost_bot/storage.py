"""Where a chat's session lives between two taps.

A session is small and cheap to lose: the theme, the level, the
questions/tasks split and whether the 18+ warning was accepted. Every card
button carries its own theme, level and index in its `callback_data`, so a
lost session costs the 18+ question once more and little else.

There are two stores, one chosen when the process first needs a session and
never mixed:

- **Memory**, the default, and what production runs: this process's own
  dictionary. Each entry is forgotten `SESSION_TTL` seconds after it was
  last saved, and the dictionary holds at most `MAX_SESSIONS`, dropping the
  least recently saved first, so it cannot grow for as long as the process
  lives. It keeps sessions serialized, so every read hands out a fresh copy
  exactly as Redis does: code that only worked because two reads returned
  one object (the reset button did, see `callback_handlers`) fails here, in
  the tests, rather than only behind Redis.
- **Redis**, only when `REDIS_URL` is set: a `redis.asyncio` client made
  from that URL, with a timeout on every call, and keys that expire after
  `SESSION_TTL`. A failure is reported, not hidden: it reaches the caller,
  and the player is told something went wrong. Nothing falls back to
  memory, which would split one chat's state across two stores, and nothing
  starts a server. This module used to launch `redis-server` itself,
  synchronously, twice, freezing the bot's event loop for six seconds to a
  minute and a half on every start, while ignoring `REDIS_URL` altogether.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from .config import settings
from .i18n import Language
from .models import SessionState

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# The memory store's ceiling. A session serializes to about two hundred
# bytes, so this is a few megabytes at most, and it is far more chats than
# are ever mid-game within one SESSION_TTL.
MAX_SESSIONS = 20_000

# How long one Redis call may take, connecting included. A tap waits on it,
# so a Redis that has gone away must cost seconds, not the minute or so a
# TCP connect can hang for.
REDIS_TIMEOUT_SECONDS = 3.0

_KEY_PREFIX = "session:"


class SessionStore(Protocol):
    """What the bot needs from wherever sessions are kept."""

    kind: str

    async def get_session(self, chat_id: int) -> SessionState | None: ...

    async def save_session(self, chat_id: int, session: SessionState) -> None: ...

    async def delete_session(self, chat_id: int) -> None: ...

    async def close(self) -> None: ...


def _dump(session: SessionState) -> str:
    return session.model_dump_json()


def _load(raw: str | bytes, chat_id: int) -> SessionState | None:
    """A stored session, or None when what is stored cannot be read.

    Unreadable is treated as absent rather than as an outage: the player
    starts from a fresh session instead of hitting an error on every tap
    until the entry expires. A session written before the product went
    Russian-only carries `en` or `cs`, which `Language.coerce` reads back
    as Russian instead of failing validation.
    """
    try:
        data: dict[str, Any] = json.loads(raw)
        if "language" in data:
            data["language"] = Language.coerce(data["language"])
        return SessionState.model_validate(data)
    except (ValueError, TypeError) as e:
        logger.warning(f"Discarding an unreadable session for chat {chat_id}: {e}")
        return None


class MemorySessionStore:
    """Sessions in this process, bounded in both time and number."""

    kind = "memory"

    def __init__(
        self,
        ttl: float,
        max_sessions: int = MAX_SESSIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._clock = clock
        # chat id -> (expires at, serialized session), oldest save first.
        # Every entry lives for the same TTL, so the front of this order is
        # also the next entry to expire, which keeps the purge in `_evict`
        # to the few entries at the front.
        self._rows: OrderedDict[int, tuple[float, str]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._rows)

    async def get_session(self, chat_id: int) -> SessionState | None:
        row = self._rows.get(chat_id)
        if row is None:
            return None
        expires_at, raw = row
        if expires_at <= self._clock():
            del self._rows[chat_id]
            return None
        session = _load(raw, chat_id)
        if session is None:
            del self._rows[chat_id]
        return session

    async def save_session(self, chat_id: int, session: SessionState) -> None:
        self._rows[chat_id] = (self._clock() + self._ttl, _dump(session))
        self._rows.move_to_end(chat_id)
        self._evict()

    async def delete_session(self, chat_id: int) -> None:
        self._rows.pop(chat_id, None)

    async def close(self) -> None:
        self._rows.clear()

    def _evict(self) -> None:
        """Drop what has expired, then the oldest past the ceiling."""
        now = self._clock()
        while self._rows:
            oldest_expires_at, _ = next(iter(self._rows.values()))
            if oldest_expires_at > now and len(self._rows) <= self._max_sessions:
                break
            self._rows.popitem(last=False)


class RedisSessionStore:
    """Sessions in the Redis that REDIS_URL names."""

    kind = "redis"

    def __init__(
        self,
        url: str,
        ttl: int,
        *,
        db: int = 0,
        max_connections: int = 20,
        timeout: float = REDIS_TIMEOUT_SECONDS,
    ) -> None:
        import redis.asyncio as redis
        from redis.asyncio.retry import Retry
        from redis.backoff import NoBackoff
        from redis.exceptions import ConnectionError as RedisConnectionError

        self._ttl = ttl
        # A blocking pool: past `max_connections` a caller waits for a free
        # connection (for at most `timeout`) instead of failing outright with
        # "Too many connections", which is what a plain pool does the moment
        # more chats than that are handled at once. One immediate retry on a
        # dropped connection (Redis restarted, a proxy closed an idle
        # socket) and none on a timeout, so a Redis that is not there costs
        # a tap about `timeout`, not a backoff schedule.
        pool = redis.BlockingConnectionPool.from_url(
            url,
            db=db,
            max_connections=max_connections,
            timeout=timeout,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            health_check_interval=30,
            decode_responses=True,
            retry=Retry(NoBackoff(), 1),
            retry_on_error=[RedisConnectionError],
        )
        self._client: Redis = redis.Redis(connection_pool=pool)

    @staticmethod
    def _key(chat_id: int) -> str:
        return f"{_KEY_PREFIX}{chat_id}"

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def get_session(self, chat_id: int) -> SessionState | None:
        raw = await self._client.get(self._key(chat_id))
        return _load(raw, chat_id) if raw is not None else None

    async def save_session(self, chat_id: int, session: SessionState) -> None:
        await self._client.set(self._key(chat_id), _dump(session), ex=self._ttl)

    async def delete_session(self, chat_id: int) -> None:
        await self._client.delete(self._key(chat_id))

    async def close(self) -> None:
        # The pool was handed to the client, so the client does not own it
        # and would leave it open unless told otherwise.
        await self._client.aclose(close_connection_pool=True)


def configured_store() -> SessionStore:
    """The store the settings ask for: Redis only when REDIS_URL is set."""
    if settings.redis_url:
        return RedisSessionStore(
            str(settings.redis_url),
            settings.session_ttl,
            db=settings.redis_db,
            max_connections=settings.max_connections,
        )
    return MemorySessionStore(settings.session_ttl)


_store: SessionStore | None = None


def session_store() -> SessionStore:
    """The store this process uses, chosen on first use and kept."""
    global _store
    if _store is None:
        _store = configured_store()
    return _store


async def close_session_store() -> None:
    """Release the store's connections, if it has any. Safe to call twice."""
    global _store
    store, _store = _store, None
    if store is not None:
        await store.close()


async def get_session(chat_id: int) -> SessionState:
    """The chat's session, or a fresh one when it has none.

    A fresh session is not written back: it is exactly what a missing one
    means, and whoever changes it saves it (the callback registry saves after
    every handler).
    """
    session = await session_store().get_session(chat_id)
    return session if session is not None else SessionState()


async def save_session(chat_id: int, session: SessionState) -> None:
    """Keep the chat's session for another SESSION_TTL."""
    await session_store().save_session(chat_id, session)


async def delete_session(chat_id: int) -> None:
    """Forget the chat's session now."""
    await session_store().delete_session(chat_id)
