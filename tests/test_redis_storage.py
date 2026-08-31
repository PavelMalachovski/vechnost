"""Tests for Redis storage implementation."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from vechnost_bot.models import Language, SessionState, Theme
from vechnost_bot.redis_storage import (
    RedisStorage,
    cleanup_redis_storage,
    get_redis_storage,
    initialize_redis_storage,
)

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


@pytest_asyncio.fixture
async def redis_storage_instance():
    """A connected client on the test database, empty at both ends.

    Module-level so every class here can use it — it used to live inside
    TestRedisStorage, which is why the performance class errored on a missing
    fixture. Flushing matters: counters and rate limits are keyed by name, so
    without it a second run of test_counter_operations starts from whatever
    the first left behind and asserts 13 == 5.
    """
    storage = RedisStorage("redis://localhost:6379", db=_test_db())
    await storage.connect()
    await storage._redis.flushdb()
    try:
        yield storage
    finally:
        await storage._redis.flushdb()
        await storage.disconnect()


class TestRedisStorage:
    """Test Redis storage functionality."""

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_storage_instance):
        """Test Redis connection."""
        await redis_storage_instance.connect()
        assert redis_storage_instance._redis is not None
        assert await redis_storage_instance.health_check() is True
        await redis_storage_instance.disconnect()

    @pytest.mark.asyncio
    async def test_session_operations(self, redis_storage_instance):
        """Test session save/get/delete operations."""
        chat_id = 12345
        session = SessionState(
            language=Language.RUSSIAN,
            theme=Theme.ACQUAINTANCE,
            level=1,
        )

        # Save session
        await redis_storage_instance.save_session(chat_id, session, ttl=60)

        # Get session
        retrieved_session = await redis_storage_instance.get_session(chat_id)
        assert retrieved_session is not None
        assert retrieved_session.language == Language.RUSSIAN
        assert retrieved_session.theme == Theme.ACQUAINTANCE
        assert retrieved_session.level == 1

        # Delete session
        await redis_storage_instance.delete_session(chat_id)
        deleted_session = await redis_storage_instance.get_session(chat_id)
        assert deleted_session is None

    @pytest.mark.asyncio
    async def test_user_stats(self, redis_storage_instance):
        """Test user statistics operations."""
        chat_id = 12345
        stats = {
            "questions_answered": 25,
            "themes_completed": 2,
            "total_time": 1800,
            "last_activity": "2024-01-01T12:00:00Z"
        }

        # Update stats
        await redis_storage_instance.update_user_stats(chat_id, stats)

        # Get stats
        retrieved_stats = await redis_storage_instance.get_user_stats(chat_id)
        assert retrieved_stats == stats

    @pytest.mark.asyncio
    async def test_image_caching(self, redis_storage_instance):
        """Test image caching functionality."""
        cache_key = "test_image_key"
        image_data = b"fake_image_data"

        # Cache image
        await redis_storage_instance.cache_rendered_image(cache_key, image_data, ttl=60)

        # Get cached image
        retrieved_data = await redis_storage_instance.get_cached_image(cache_key)
        assert retrieved_data == image_data

    @pytest.mark.asyncio
    async def test_caching_an_actual_image(self, redis_storage_instance):
        """Bytes that are not text survive the round trip.

        The test above passes `b"fake_image_data"` - pure ASCII, which came
        back intact through a UTF-8 encode and decode by luck, and so the
        cache looked fine while it had never once returned a real image. The
        pool is opened with `decode_responses=True`, so a JPEG read straight
        back died on `'utf-8' codec can't decode byte 0x89` inside the
        method's own try/except and became a silent None. Every byte from
        0x80 up is the case that matters, so this uses a real file.
        """
        image_data = Path("assets/backgrounds/acq/acq_1.png").read_bytes()
        assert any(byte > 0x7F for byte in image_data[:16]), "needs non-ASCII bytes"

        await redis_storage_instance.cache_rendered_image("real_png", image_data, ttl=60)

        assert await redis_storage_instance.get_cached_image("real_png") == image_data

    @pytest.mark.asyncio
    async def test_a_cache_miss_is_none(self, redis_storage_instance):
        """And a key that was never written is a miss, not an error."""
        assert await redis_storage_instance.get_cached_image("nothing_here") is None

    @pytest.mark.asyncio
    async def test_counter_operations(self, redis_storage_instance):
        """Test counter operations."""
        counter_name = "test_counter"

        # Increment counter
        result1 = await redis_storage_instance.increment_counter(counter_name, 5)
        assert result1 == 5

        result2 = await redis_storage_instance.increment_counter(counter_name, 3)
        assert result2 == 8

    @pytest.mark.asyncio
    async def test_rate_limiting(self, redis_storage_instance):
        """Test rate limiting functionality."""
        user_id = 12345
        limit = 10
        period = 60

        # Set rate limit
        await redis_storage_instance.set_rate_limit(user_id, 5, period)

        # Get rate limit info
        info = await redis_storage_instance.get_rate_limit_info(user_id, limit, period)
        assert info["count"] == 5
        assert info["limit"] == limit
        assert info["remaining"] == 5

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        """Test handling of connection failures."""
        storage = RedisStorage("redis://invalid-host:6379")

        # Should handle connection failure gracefully
        session = await storage.get_session(12345)
        assert session is None

        # Should not raise exception
        await storage.save_session(12345, SessionState(), ttl=60)

    @pytest.mark.asyncio
    async def test_global_storage_functions(self):
        """Test global storage functions."""
        with patch('vechnost_bot.redis_storage.redis_storage') as mock_storage:
            mock_storage._redis = None
            mock_storage.connect = AsyncMock()

            storage = await get_redis_storage()
            assert storage is not None
            mock_storage.connect.assert_called_once()


class TestRedisIntegration:
    """Test Redis integration with the bot."""

    @pytest.mark.asyncio
    async def test_initialize_redis_storage(self):
        """Test Redis storage initialization."""
        with patch('vechnost_bot.redis_storage.RedisStorage') as mock_storage_class:
            mock_storage = AsyncMock()
            mock_storage.connect = AsyncMock()
            mock_storage_class.return_value = mock_storage

            await initialize_redis_storage("redis://localhost:6379", db=1)

            mock_storage_class.assert_called_once_with("redis://localhost:6379", 1)
            mock_storage.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_redis_storage(self):
        """Test Redis storage cleanup."""
        with patch('vechnost_bot.redis_storage.redis_storage') as mock_storage:
            mock_storage.disconnect = AsyncMock()

            await cleanup_redis_storage()

            mock_storage.disconnect.assert_called_once()


class TestRedisPerformance:
    """Test Redis performance characteristics."""

    @pytest.mark.asyncio
    async def test_batch_operations(self, redis_storage_instance):
        """Many sessions at once, within the pool the app actually runs.

        The pool is capped at `settings.max_connections`, so firing more
        concurrent operations than that raises "Too many connections" — from
        the pool, not from Redis. Testing above the cap measured nothing the
        bot can do; the batch is sized to the pool instead.
        """
        from vechnost_bot.config import settings

        first = 1000
        chat_ids = list(range(first, first + settings.max_connections))
        sessions = [
            SessionState(language=Language.RUSSIAN) for _ in chat_ids
        ]

        # Batch save
        start_time = asyncio.get_event_loop().time()
        tasks = [
            redis_storage_instance.save_session(chat_id, session, ttl=60)
            for chat_id, session in zip(chat_ids, sessions, strict=True)
        ]
        await asyncio.gather(*tasks)
        save_time = asyncio.get_event_loop().time() - start_time

        # Batch get
        start_time = asyncio.get_event_loop().time()
        tasks = [
            redis_storage_instance.get_session(chat_id)
            for chat_id in chat_ids
        ]
        results = await asyncio.gather(*tasks)
        get_time = asyncio.get_event_loop().time() - start_time

        # Verify all sessions were saved and retrieved
        assert all(result is not None for result in results)
        assert save_time < 1.0  # Should be fast
        assert get_time < 1.0   # Should be fast

        # Cleanup
        tasks = [
            redis_storage_instance.delete_session(chat_id)
            for chat_id in chat_ids
        ]
        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_memory_usage(self, redis_storage_instance):
        """Test memory usage patterns."""
        # Create large session data
        large_data = {
            "large_field": "x" * 10000,  # 10KB string
            "array_field": list(range(1000))  # 1000 integers
        }

        session = SessionState(chat_id=12345, language=Language.RUSSIAN)
        session_dict = session.dict()
        session_dict.update(large_data)

        # This should work without issues
        await redis_storage_instance.save_session(12345, session, ttl=60)
        retrieved = await redis_storage_instance.get_session(12345)
        assert retrieved is not None

        # Cleanup
        await redis_storage_instance.delete_session(12345)
