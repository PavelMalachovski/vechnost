"""Redis-based storage implementation for the Vechnost bot."""

import json
import asyncio
from typing import Optional, Dict, Any
import redis.asyncio as redis
import structlog
from datetime import timedelta

from .models import SessionState, Language, Theme
from .config import settings

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
        self._redis: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None

    async def connect(self):
        """Establish Redis connection with connection pooling."""
        try:
            # Create connection pool with optimal settings
            self._connection_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                db=self.db,
                decode_responses=True,
                max_connections=settings.max_connections,
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

    async def disconnect(self):
        """Close Redis connection and cleanup resources."""
        if self._redis:
            await self._redis.aclose()
        if self._connection_pool:
            await self._connection_pool.aclose()
        logger.info("redis_disconnected")

    async def get_session(self, chat_id: int) -> Optional[SessionState]:
        """Get user session from Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"session:{chat_id}"
            data = await self._redis.get(key)

            if data:
                session_dict = json.loads(data)
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
            if not self._redis:
                await self.connect()

            key = f"session:{chat_id}"
            data = json.dumps(session.dict(), default=str)

            await self._redis.setex(key, ttl, data)
            logger.debug("session_saved", chat_id=chat_id, ttl=ttl)

        except Exception as e:
            logger.error("redis_save_session_error", chat_id=chat_id, error=str(e))

    async def delete_session(self, chat_id: int):
        """Delete user session from Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"session:{chat_id}"
            await self._redis.delete(key)
            logger.debug("session_deleted", chat_id=chat_id)

        except Exception as e:
            logger.error("redis_delete_session_error", chat_id=chat_id, error=str(e))

    async def get_user_stats(self, chat_id: int) -> Dict[str, Any]:
        """Get user statistics from Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"stats:{chat_id}"
            data = await self._redis.get(key)

            if data:
                return json.loads(data)
            return {}

        except Exception as e:
            logger.error("redis_get_stats_error", chat_id=chat_id, error=str(e))
            return {}

    async def update_user_stats(self, chat_id: int, stats: Dict[str, Any]):
        """Update user statistics in Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"stats:{chat_id}"
            data = json.dumps(stats)
            await self._redis.setex(key, 86400 * 30, data)  # 30 days TTL

        except Exception as e:
            logger.error("redis_update_stats_error", chat_id=chat_id, error=str(e))

    async def cache_rendered_image(self, cache_key: str, image_data: bytes, ttl: int = 3600):
        """Cache rendered image in Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"image:{cache_key}"
            await self._redis.setex(key, ttl, image_data)
            logger.debug("image_cached", cache_key=cache_key, ttl=ttl)

        except Exception as e:
            logger.error("redis_cache_image_error", cache_key=cache_key, error=str(e))

    async def get_cached_image(self, cache_key: str) -> Optional[bytes]:
        """Get cached image from Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"image:{cache_key}"
            data = await self._redis.get(key)
            return data.encode() if data else None

        except Exception as e:
            logger.error("redis_get_image_error", cache_key=cache_key, error=str(e))
            return None

    async def increment_counter(self, counter_name: str, increment: int = 1) -> int:
        """Increment a counter in Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"counter:{counter_name}"
            result = await self._redis.incrby(key, increment)
            await self._redis.expire(key, 86400)  # 24 hours TTL
            return result

        except Exception as e:
            logger.error("redis_increment_counter_error", counter=counter_name, error=str(e))
            return 0

    async def get_rate_limit_info(self, user_id: int, limit: int, period: int) -> Dict[str, Any]:
        """Get rate limit information from Redis."""
        try:
            if not self._redis:
                await self.connect()

            key = f"rate_limit:{user_id}"
            current_count = await self._redis.get(key)
            ttl = await self._redis.ttl(key)

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
            if not self._redis:
                await self.connect()

            key = f"rate_limit:{user_id}"
            await self._redis.setex(key, period, count)

        except Exception as e:
            logger.error("redis_set_rate_limit_error", user_id=user_id, error=str(e))

    async def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            if not self._redis:
                await self.connect()

            await self._redis.ping()
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
