"""Tests for Redis storage implementation."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from vechnost_bot.redis_storage import RedisStorage, redis_storage, initialize_redis_storage, cleanup_redis_storage
from vechnost_bot.models import SessionState, Language, Theme


class TestRedisStorage:
    """Test Redis storage functionality."""

    @pytest.fixture
    def redis_storage_instance(self):
        """Create Redis storage instance for testing."""
        return RedisStorage("redis://localhost:6379", db=15)  # Use test DB

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
            chat_id=chat_id,
            language=Language.ENGLISH,
            theme=Theme.ACQUAINTANCE,
            level=1,
            current_question=5
        )

        # Save session
        await redis_storage_instance.save_session(chat_id, session, ttl=60)

        # Get session
        retrieved_session = await redis_storage_instance.get_session(chat_id)
        assert retrieved_session is not None
        assert retrieved_session.chat_id == chat_id
        assert retrieved_session.language == Language.ENGLISH
        assert retrieved_session.theme == Theme.ACQUAINTANCE
        assert retrieved_session.level == 1
        assert retrieved_session.current_question == 5

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
        await storage.save_session(12345, SessionState(chat_id=12345), ttl=60)

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

            mock_storage_class.assert_called_once_with("redis://localhost:6379", db=1)
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
        """Test batch operations performance."""
        chat_ids = list(range(1000, 1100))  # 100 sessions
        sessions = [
            SessionState(chat_id=chat_id, language=Language.ENGLISH)
            for chat_id in chat_ids
        ]

        # Batch save
        start_time = asyncio.get_event_loop().time()
        tasks = [
            redis_storage_instance.save_session(chat_id, session, ttl=60)
            for chat_id, session in zip(chat_ids, sessions)
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

        session = SessionState(chat_id=12345, language=Language.ENGLISH)
        session_dict = session.dict()
        session_dict.update(large_data)

        # This should work without issues
        await redis_storage_instance.save_session(12345, session, ttl=60)
        retrieved = await redis_storage_instance.get_session(12345)
        assert retrieved is not None

        # Cleanup
        await redis_storage_instance.delete_session(12345)
