"""Hybrid storage implementation with Redis auto-start and fallback to in-memory storage."""

import asyncio
from typing import Optional, Dict, Any
import structlog
from datetime import datetime, timedelta

from .models import SessionState, Language, Theme
from .redis_storage import RedisStorage
from .simple_redis_manager import simple_redis_auto_start_manager, get_simple_redis_connection_url
from .config import settings

logger = structlog.get_logger(__name__)


class InMemoryStorage:
    """In-memory storage fallback when Redis is unavailable."""

    def __init__(self):
        self.sessions: Dict[int, SessionState] = {}
        self.user_stats: Dict[int, Dict[str, Any]] = {}
        self.image_cache: Dict[str, bytes] = {}
        self.counters: Dict[str, int] = {}
        self.rate_limits: Dict[int, Dict[str, Any]] = {}

    async def get_session(self, chat_id: int) -> Optional[SessionState]:
        """Get session from memory."""
        return self.sessions.get(chat_id)

    async def save_session(self, chat_id: int, session: SessionState, ttl: int = None):
        """Save session to memory."""
        self.sessions[chat_id] = session
        logger.debug("session_saved_in_memory", chat_id=chat_id)

    async def delete_session(self, chat_id: int):
        """Delete session from memory."""
        self.sessions.pop(chat_id, None)
        logger.debug("session_deleted_from_memory", chat_id=chat_id)

    async def get_user_stats(self, chat_id: int) -> Dict[str, Any]:
        """Get user stats from memory."""
        return self.user_stats.get(chat_id, {})

    async def update_user_stats(self, chat_id: int, stats: Dict[str, Any]):
        """Update user stats in memory."""
        self.user_stats[chat_id] = stats

    async def cache_rendered_image(self, cache_key: str, image_data: bytes, ttl: int = 3600):
        """Cache image in memory."""
        self.image_cache[cache_key] = image_data
        logger.debug("image_cached_in_memory", cache_key=cache_key)

    async def get_cached_image(self, cache_key: str) -> Optional[bytes]:
        """Get cached image from memory."""
        return self.image_cache.get(cache_key)

    async def increment_counter(self, counter_name: str, increment: int = 1) -> int:
        """Increment counter in memory."""
        current = self.counters.get(counter_name, 0)
        self.counters[counter_name] = current + increment
        return self.counters[counter_name]

    async def get_rate_limit_info(self, user_id: int, limit: int, period: int) -> Dict[str, Any]:
        """Get rate limit info from memory."""
        user_data = self.rate_limits.get(user_id, {})
        current_count = user_data.get('count', 0)
        last_reset = user_data.get('last_reset', datetime.now())

        # Check if period has passed
        if datetime.now() - last_reset > timedelta(seconds=period):
            current_count = 0
            self.rate_limits[user_id] = {'count': 0, 'last_reset': datetime.now()}

        return {
            "count": current_count,
            "limit": limit,
            "period": period,
            "remaining": max(0, limit - current_count),
            "reset_in": period
        }

    async def set_rate_limit(self, user_id: int, count: int, period: int):
        """Set rate limit in memory."""
        self.rate_limits[user_id] = {
            'count': count,
            'last_reset': datetime.now()
        }

    async def health_check(self) -> bool:
        """Memory storage is always healthy."""
        return True


class HybridStorage:
    """Hybrid storage with Redis auto-start and fallback to in-memory."""

    def __init__(self):
        self.redis_storage: Optional[RedisStorage] = None
        self.memory_storage = InMemoryStorage()
        self._redis_available = False
        self._redis_checked = False
        self._initialized = False

    async def _ensure_redis_connection(self) -> bool:
        """Ensure Redis connection is available with auto-start."""
        if self._redis_checked:
            return self._redis_available

        try:
            # Initialize Redis auto-start if not done yet
            if not self._initialized:
                simple_redis_auto_start_manager.initialize()
                self._initialized = True

            # Get Redis connection URL (will be valid if Redis is running)
            redis_url = get_simple_redis_connection_url()

            if not self.redis_storage:
                self.redis_storage = RedisStorage(redis_url=redis_url)

            await self.redis_storage.connect()
            self._redis_available = True
            logger.info("redis_connection_established", url=redis_url)
        except Exception as e:
            logger.warning("redis_connection_failed", error=str(e))
            self._redis_available = False
            # Reset the checked flag so we can retry later
            self._redis_checked = False
        finally:
            if self._redis_available:
                self._redis_checked = True

        return self._redis_available

    async def get_session(self, chat_id: int) -> Optional[SessionState]:
        """Get session with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                return await self.redis_storage.get_session(chat_id)
            except Exception as e:
                logger.warning("redis_get_session_failed", error=str(e))
                return await self.memory_storage.get_session(chat_id)
        else:
            return await self.memory_storage.get_session(chat_id)

    async def save_session(self, chat_id: int, session: SessionState, ttl: int = None):
        """Save session with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                await self.redis_storage.save_session(chat_id, session, ttl)
            except Exception as e:
                logger.warning("redis_save_session_failed", error=str(e))
                await self.memory_storage.save_session(chat_id, session, ttl)
        else:
            await self.memory_storage.save_session(chat_id, session, ttl)

    async def delete_session(self, chat_id: int):
        """Delete session with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                await self.redis_storage.delete_session(chat_id)
            except Exception as e:
                logger.warning("redis_delete_session_failed", error=str(e))
                await self.memory_storage.delete_session(chat_id)
        else:
            await self.memory_storage.delete_session(chat_id)

    async def get_user_stats(self, chat_id: int) -> Dict[str, Any]:
        """Get user stats with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                return await self.redis_storage.get_user_stats(chat_id)
            except Exception as e:
                logger.warning("redis_get_stats_failed", error=str(e))
                return await self.memory_storage.get_user_stats(chat_id)
        else:
            return await self.memory_storage.get_user_stats(chat_id)

    async def update_user_stats(self, chat_id: int, stats: Dict[str, Any]):
        """Update user stats with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                await self.redis_storage.update_user_stats(chat_id, stats)
            except Exception as e:
                logger.warning("redis_update_stats_failed", error=str(e))
                await self.memory_storage.update_user_stats(chat_id, stats)
        else:
            await self.memory_storage.update_user_stats(chat_id, stats)

    async def cache_rendered_image(self, cache_key: str, image_data: bytes, ttl: int = 3600):
        """Cache image with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                await self.redis_storage.cache_rendered_image(cache_key, image_data, ttl)
            except Exception as e:
                logger.warning("redis_cache_image_failed", error=str(e))
                await self.memory_storage.cache_rendered_image(cache_key, image_data, ttl)
        else:
            await self.memory_storage.cache_rendered_image(cache_key, image_data, ttl)

    async def get_cached_image(self, cache_key: str) -> Optional[bytes]:
        """Get cached image with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                return await self.redis_storage.get_cached_image(cache_key)
            except Exception as e:
                logger.warning("redis_get_image_failed", error=str(e))
                return await self.memory_storage.get_cached_image(cache_key)
        else:
            return await self.memory_storage.get_cached_image(cache_key)

    async def increment_counter(self, counter_name: str, increment: int = 1) -> int:
        """Increment counter with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                return await self.redis_storage.increment_counter(counter_name, increment)
            except Exception as e:
                logger.warning("redis_increment_counter_failed", error=str(e))
                return await self.memory_storage.increment_counter(counter_name, increment)
        else:
            return await self.memory_storage.increment_counter(counter_name, increment)

    async def get_rate_limit_info(self, user_id: int, limit: int, period: int) -> Dict[str, Any]:
        """Get rate limit info with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                return await self.redis_storage.get_rate_limit_info(user_id, limit, period)
            except Exception as e:
                logger.warning("redis_rate_limit_failed", error=str(e))
                return await self.memory_storage.get_rate_limit_info(user_id, limit, period)
        else:
            return await self.memory_storage.get_rate_limit_info(user_id, limit, period)

    async def set_rate_limit(self, user_id: int, count: int, period: int):
        """Set rate limit with Redis fallback to memory."""
        if await self._ensure_redis_connection():
            try:
                await self.redis_storage.set_rate_limit(user_id, count, period)
            except Exception as e:
                logger.warning("redis_set_rate_limit_failed", error=str(e))
                await self.memory_storage.set_rate_limit(user_id, count, period)
        else:
            await self.memory_storage.set_rate_limit(user_id, count, period)

    async def health_check(self) -> bool:
        """Check health of storage system."""
        if await self._ensure_redis_connection():
            try:
                return await self.redis_storage.health_check()
            except Exception as e:
                logger.warning("redis_health_check_failed", error=str(e))
                return await self.memory_storage.health_check()
        else:
            return await self.memory_storage.health_check()


# Global hybrid storage instance
hybrid_storage = HybridStorage()


async def get_redis_storage():
    """Get hybrid storage instance (Redis with memory fallback)."""
    return hybrid_storage


async def initialize_redis_storage(redis_url: str = None, db: int = None):
    """Initialize hybrid storage."""
    global hybrid_storage
    hybrid_storage = HybridStorage()
    logger.info("hybrid_storage_initialized")


async def cleanup_redis_storage():
    """Cleanup hybrid storage."""
    if hybrid_storage.redis_storage:
        await hybrid_storage.redis_storage.disconnect()
    logger.info("hybrid_storage_cleanup_completed")
