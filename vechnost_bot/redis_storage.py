"""Redis-based storage implementation for the Vechnost bot."""

import base64
import json
from typing import Any

import redis.asyncio as redis
import structlog

from .config import settings
from .exceptions import RedisConnectionError
from .models import Language, SessionState

logger = structlog.get_logger(__name__)


class RedisStorage:
    """Redis-based storage for user sessions and game data."""

    def __init__(self, redis_url: str = None, db: int = None):
        """
        Initialize Redis storage.

        Args:
            redis_url: Redis connection URL (defaults to settings)
            db: Redis database number (defaults to settings)
        """
        self.redis_url = redis_url or str(settings.redis_url)
        self.db = db or settings.redis_db
        self._redis: redis.Redis | None = None
        self._connection_pool: redis.ConnectionPool | None = None

    async def connect(self):
        """Establish Redis connection with connection pooling."""
        try:
            # BlockingConnectionPool, not ConnectionPool. A plain pool raises
            # "Too many connections" the moment demand passes max_connections,
            # so a burst of concurrent chats did not queue — it lost sessions,
            # silently, with the error swallowed by the caller's try/except.
            # Blocking makes the twentieth caller wait for a free connection
            # instead, which is what a pool is for; `timeout` keeps a wait
            # from becoming a hang.
            self._connection_pool = redis.BlockingConnectionPool.from_url(
                self.redis_url,
                db=self.db,
                decode_responses=True,
                max_connections=settings.max_connections,
                timeout=5,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )

            # Create Redis client from pool
            self._redis = redis.Redis(connection_pool=self._connection_pool)

            # Test connection
            await self._redis.ping()
            logger.info("redis_connected", url=self.redis_url, db=self.db)

        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise

    async def _client(self) -> redis.Redis:
        """The connected client, connecting on first use.

        Every method below opened with `if not self._redis: await
        self.connect()` and then used `self._redis` directly - correct, but
        the connection and the use were two statements apart, so nothing but
        reading the pair told you the client was really there. Fourteen
        places relied on that. This makes it one statement and one type.
        """
        if self._redis is None:
            await self.connect()
        if self._redis is None:
            # connect() raises rather than returning without a client, so
            # this is unreachable - and says so out loud instead of letting
            # a None reach the call below as an AttributeError.
            raise RedisConnectionError("Redis client is not connected")
        return self._redis

    async def disconnect(self):
        """Close Redis connection and cleanup resources."""
        if self._redis:
            await self._redis.aclose()
        if self._connection_pool:
            await self._connection_pool.aclose()
        logger.info("redis_disconnected")

    async def get_session(self, chat_id: int) -> SessionState | None:
        """Get user session from Redis."""
        try:
            client = await self._client()

            key = f"session:{chat_id}"
            data = await client.get(key)

            if data:
                session_dict = json.loads(data)
                # Convert list back to set for drawn_cards
                if 'drawn_cards' in session_dict and isinstance(session_dict['drawn_cards'], list):
                    session_dict['drawn_cards'] = set(session_dict['drawn_cards'])
                # A session written before the product went Russian-only carries
                # `en`/`cs`. `SessionState(language='en')` raises, the `except`
                # below swallows it, and the caller gets None — the user's theme,
                # level, position, drawn cards and 18+ confirmation are silently
                # discarded mid-game, with an ERROR logged on every read. This is
                # the deserialization path `Language.coerce` exists for.
                if 'language' in session_dict:
                    session_dict['language'] = Language.coerce(session_dict['language'])
                return SessionState(**session_dict)
            return None

        except Exception as e:
            logger.error("redis_get_session_error", chat_id=chat_id, error=str(e))
            return None

    async def save_session(self, chat_id: int, session: SessionState, ttl: int = None):
        """
        Save user session to Redis with TTL.

        Args:
            chat_id: User's chat ID
            session: Session state to save
            ttl: Time to live in seconds (defaults to settings)
        """
        if ttl is None:
            ttl = settings.session_ttl
        try:
            client = await self._client()

            key = f"session:{chat_id}"
            # Convert set to list for JSON serialization
            session_dict = session.dict()
            if 'drawn_cards' in session_dict and isinstance(session_dict['drawn_cards'], set):
                session_dict['drawn_cards'] = list(session_dict['drawn_cards'])

            data = json.dumps(session_dict, default=str)

            await client.setex(key, ttl, data)
            logger.debug("session_saved", chat_id=chat_id, ttl=ttl)

        except Exception as e:
            logger.error("redis_save_session_error", chat_id=chat_id, error=str(e))

    async def delete_session(self, chat_id: int):
        """Delete user session from Redis."""
        try:
            client = await self._client()

            key = f"session:{chat_id}"
            await client.delete(key)
            logger.debug("session_deleted", chat_id=chat_id)

        except Exception as e:
            logger.error("redis_delete_session_error", chat_id=chat_id, error=str(e))

    async def get_user_stats(self, chat_id: int) -> dict[str, Any]:
        """Get user statistics from Redis."""
        try:
            client = await self._client()

            key = f"stats:{chat_id}"
            data = await client.get(key)

            if data:
                return json.loads(data)
            return {}

        except Exception as e:
            logger.error("redis_get_stats_error", chat_id=chat_id, error=str(e))
            return {}

    async def update_user_stats(self, chat_id: int, stats: dict[str, Any]):
        """Update user statistics in Redis."""
        try:
            client = await self._client()

            key = f"stats:{chat_id}"
            data = json.dumps(stats)
            await client.setex(key, 86400 * 30, data)  # 30 days TTL

        except Exception as e:
            logger.error("redis_update_stats_error", chat_id=chat_id, error=str(e))

    async def cache_rendered_image(self, cache_key: str, image_data: bytes, ttl: int = 3600):
        """Cache rendered image in Redis, base64 over a text connection.

        The pool is opened with `decode_responses=True`, because everything
        else stored here is JSON. That makes the connection UTF-8, and a JPEG
        is not UTF-8: written raw and read back, every image died on
        `'utf-8' codec can't decode byte 0x89` inside the read's own
        try/except, so the cache returned None every single time while still
        paying for the write. Base64 costs a third more bytes and is the only
        thing that survives the trip.
        """
        try:
            client = await self._client()

            key = f"image:{cache_key}"
            await client.setex(key, ttl, base64.b64encode(image_data).decode("ascii"))
            logger.debug("image_cached", cache_key=cache_key, ttl=ttl)

        except Exception as e:
            logger.error("redis_cache_image_error", cache_key=cache_key, error=str(e))

    async def get_cached_image(self, cache_key: str) -> bytes | None:
        """Get cached image from Redis."""
        try:
            client = await self._client()

            key = f"image:{cache_key}"
            data = await client.get(key)
            # `.encode()` was here, which is not the inverse of anything: it
            # would have re-encoded the text as UTF-8 rather than recovering
            # the bytes that went in.
            return base64.b64decode(data) if data else None

        except Exception as e:
            logger.error("redis_get_image_error", cache_key=cache_key, error=str(e))
            return None

    async def increment_counter(self, counter_name: str, increment: int = 1) -> int:
        """Increment a counter in Redis."""
        try:
            client = await self._client()

            key = f"counter:{counter_name}"
            result = await client.incrby(key, increment)
            await client.expire(key, 86400)  # 24 hours TTL
            return result

        except Exception as e:
            logger.error("redis_increment_counter_error", counter=counter_name, error=str(e))
            return 0

    async def get_rate_limit_info(self, user_id: int, limit: int, period: int) -> dict[str, Any]:
        """Get rate limit information from Redis."""
        try:
            client = await self._client()

            key = f"rate_limit:{user_id}"
            current_count = await client.get(key)
            ttl = await client.ttl(key)

            return {
                "count": int(current_count) if current_count else 0,
                "limit": limit,
                "period": period,
                "remaining": max(0, limit - int(current_count)) if current_count else limit,
                "reset_in": ttl if ttl > 0 else period
            }

        except Exception as e:
            logger.error("redis_rate_limit_error", user_id=user_id, error=str(e))
            return {"count": 0, "limit": limit, "period": period, "remaining": limit, "reset_in": period}

    async def set_rate_limit(self, user_id: int, count: int, period: int):
        """Set rate limit in Redis."""
        try:
            client = await self._client()

            key = f"rate_limit:{user_id}"
            await client.setex(key, period, count)

        except Exception as e:
            logger.error("redis_set_rate_limit_error", user_id=user_id, error=str(e))

    async def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            client = await self._client()

            await client.ping()
            return True

        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))
            return False


# Global Redis storage instance
redis_storage = RedisStorage()


async def get_redis_storage() -> RedisStorage:
    """Get Redis storage instance."""
    if not redis_storage._redis:
        await redis_storage.connect()
    return redis_storage


async def initialize_redis_storage(redis_url: str = "redis://localhost:6379", db: int = 0):
    """Initialize Redis storage."""
    global redis_storage
    redis_storage = RedisStorage(redis_url, db)
    await redis_storage.connect()
    logger.info("redis_storage_initialized")


async def cleanup_redis_storage():
    """Cleanup Redis storage."""
    await redis_storage.disconnect()
    logger.info("redis_storage_cleanup_completed")
