"""Comprehensive performance tests for Vechnost bot."""

import pytest
import pytest_asyncio
import asyncio
import time
import statistics
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from vechnost_bot.models import SessionState, Language, Theme, ContentType
from vechnost_bot.hybrid_storage import HybridStorage, InMemoryStorage
from vechnost_bot.exceptions import VechnostBotError


class TestStoragePerformance:
    """Test storage performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_save_performance(self, hybrid_storage_with_memory):
        """Test session save performance."""
        session = SessionState(
            language=Language.ENGLISH,
            theme=Theme.ACQUAINTANCE,
            level=1,
            content_type=ContentType.QUESTIONS
        )

        # Measure save performance
        start_time = time.time()
        await hybrid_storage_with_memory.save_session(12345, session)
        save_time = time.time() - start_time

        # Should complete within 100ms
        assert save_time < 0.1

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_get_performance(self, hybrid_storage_with_memory):
        """Test session get performance."""
        session = SessionState(
            language=Language.ENGLISH,
            theme=Theme.ACQUAINTANCE,
            level=1
        )
        await hybrid_storage_with_memory.save_session(12345, session)

        # Measure get performance
        start_time = time.time()
        retrieved_session = await hybrid_storage_with_memory.get_session(12345)
        get_time = time.time() - start_time

        # Should complete within 50ms
        assert get_time < 0.05
        assert retrieved_session is not None

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, hybrid_storage_with_memory):
        """Test concurrent session operations."""
        async def create_session(user_id: int):
            """Create a session for a user."""
            session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=1
            )
            await hybrid_storage_with_memory.save_session(user_id, session)
            return await hybrid_storage_with_memory.get_session(user_id)

        # Create 100 concurrent sessions
        start_time = time.time()
        user_ids = list(range(100))
        sessions = await asyncio.gather(*[
            create_session(user_id) for user_id in user_ids
        ])
        total_time = time.time() - start_time

        # Should complete within 2 seconds
        assert total_time < 2.0
        assert len(sessions) == 100

        # Verify all sessions were created correctly
        for session in sessions:
            assert session is not None
            assert session.language == Language.ENGLISH
            assert session.theme == Theme.ACQUAINTANCE

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_update_performance(self, hybrid_storage_with_memory):
        """Test session update performance."""
        session = SessionState(
            language=Language.ENGLISH,
            theme=Theme.ACQUAINTANCE,
            level=1
        )
        await hybrid_storage_with_memory.save_session(12345, session)

        # Measure update performance
        start_time = time.time()
        session.level = 2
        session.theme = Theme.FOR_COUPLES
        await hybrid_storage_with_memory.save_session(12345, session)
        update_time = time.time() - start_time

        # Should complete within 100ms
        assert update_time < 0.1

        # Verify update was successful
        updated_session = await hybrid_storage_with_memory.get_session(12345)
        assert updated_session.level == 2
        assert updated_session.theme == Theme.FOR_COUPLES

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, hybrid_storage_with_memory):
        """Test memory usage under load."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create many sessions
        sessions = []
        for i in range(1000):
            session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=1
            )
            await hybrid_storage_with_memory.save_session(i, session)
            sessions.append(await hybrid_storage_with_memory.get_session(i))

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB)
        assert memory_increase < 50 * 1024 * 1024  # 50MB

        # Verify all sessions are accessible
        assert len(sessions) == 1000
        for session in sessions:
            assert session is not None


class TestCallbackHandlerPerformance:
    """Test callback handler performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_callback_processing_performance(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test callback processing performance."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            from vechnost_bot.handlers import handle_callback_query

            callbacks = [
                "lang_en",
                "theme_Acquaintance",
                "level_1",
                "q:acq:1:0",
                "nav:next",
                "nav:prev",
                "back:calendar"
            ]

            # Measure total processing time
            start_time = time.time()
            for callback_data in callbacks:
                mock_update.callback_query.data = callback_data
                await handle_callback_query(mock_update, mock_context)
            total_time = time.time() - start_time

            # Should complete within 1 second
            assert total_time < 1.0

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_rapid_callback_handling(
        self,
        mock_update,
        mock_context,
        hybrid_storage_with_memory
    ):
        """Test rapid callback handling."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            from vechnost_bot.handlers import handle_callback_query

            # Simulate rapid callbacks
            callback_data = "lang_en"
            mock_update.callback_query.data = callback_data

            # Measure individual callback processing time
            times = []
            for _ in range(10):
                start_time = time.time()
                await handle_callback_query(mock_update, mock_context)
                end_time = time.time()
                times.append(end_time - start_time)

            # Calculate statistics
            avg_time = statistics.mean(times)
            max_time = max(times)
            min_time = min(times)

            # Performance requirements
            assert avg_time < 0.1  # Average under 100ms
            assert max_time < 0.2  # Max under 200ms
            assert min_time < 0.05  # Min under 50ms

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_callback_handling(
        self,
        hybrid_storage_with_memory
    ):
        """Test concurrent callback handling."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            from vechnost_bot.handlers import handle_callback_query

            async def handle_callback(user_id: int, callback_data: str):
                """Handle a callback for a user."""
                mock_update = MagicMock()
                mock_update.callback_query = MagicMock()
                mock_update.callback_query.data = callback_data
                mock_update.callback_query.edit_message_text = AsyncMock()
                mock_update.callback_query.answer = AsyncMock()
                mock_update.message = MagicMock()
                mock_update.message.chat = MagicMock()
                mock_update.message.chat.id = user_id
                mock_update.effective_user = MagicMock()
                mock_update.effective_user.id = user_id

                mock_context = MagicMock()

                await handle_callback_query(mock_update, mock_context)

            # Handle 50 concurrent callbacks
            start_time = time.time()
            tasks = []
            for i in range(50):
                task = handle_callback(i, "lang_en")
                tasks.append(task)

            await asyncio.gather(*tasks)
            total_time = time.time() - start_time

            # Should complete within 3 seconds
            assert total_time < 3.0


class TestImageRenderingPerformance:
    """Test image rendering performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_question_card_rendering_performance(self, mock_image_operations):
        """Test question card rendering performance."""
        with patch('vechnost_bot.renderer.render_card') as mock_render:
            mock_render.return_value = b"mock_image_data"

            # Measure rendering time
            start_time = time.time()
            image_data = await mock_render("Test question", "en")
            render_time = time.time() - start_time

            # Should complete within 500ms
            assert render_time < 0.5
            assert image_data == b"mock_image_data"

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_logo_generation_performance(self, mock_image_operations):
        """Test logo generation performance."""
        with patch('vechnost_bot.logo_generator.generate_vechnost_logo') as mock_logo:
            mock_logo.return_value = b"mock_logo_data"

            # Measure logo generation time
            start_time = time.time()
            logo_data = await mock_logo()
            logo_time = time.time() - start_time

            # Should complete within 1 second
            assert logo_time < 1.0
            assert logo_data == b"mock_logo_data"

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_image_rendering(self, mock_image_operations):
        """Test concurrent image rendering."""
        with patch('vechnost_bot.renderer.render_card') as mock_render:
            mock_render.return_value = b"mock_image_data"

            async def render_image(question: str):
                """Render an image."""
                return await mock_render(question, "en")

            # Render 20 images concurrently
            start_time = time.time()
            questions = [f"Question {i}" for i in range(20)]
            images = await asyncio.gather(*[
                render_image(question) for question in questions
            ])
            total_time = time.time() - start_time

            # Should complete within 2 seconds
            assert total_time < 2.0
            assert len(images) == 20
            for image in images:
                assert image == b"mock_image_data"


class TestMemoryPerformance:
    """Test memory performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_memory_usage(self, hybrid_storage_with_memory):
        """Test session memory usage."""
        import psutil
        import os

        process = psutil.Process(os.getpid())

        # Measure memory usage with different session counts
        memory_usage = []
        session_counts = [10, 50, 100, 500, 1000]

        for count in session_counts:
            # Clear previous sessions
            await hybrid_storage_with_memory.delete_session(12345)

            # Create sessions
            for i in range(count):
                session = SessionState(
                    language=Language.ENGLISH,
                    theme=Theme.ACQUAINTANCE,
                    level=1
                )
                await hybrid_storage_with_memory.save_session(i, session)

            # Measure memory
            memory_info = process.memory_info()
            memory_usage.append(memory_info.rss)

        # Memory usage should scale linearly
        for i in range(1, len(memory_usage)):
            memory_increase = memory_usage[i] - memory_usage[i-1]
            # Each additional session should use less than 1KB
            assert memory_increase < session_counts[i] * 1024

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_memory_cleanup_performance(self, hybrid_storage_with_memory):
        """Test memory cleanup performance."""
        # Create many sessions
        for i in range(1000):
            session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=1
            )
            await hybrid_storage_with_memory.save_session(i, session)

        # Measure cleanup time
        start_time = time.time()
        for i in range(1000):
            await hybrid_storage_with_memory.delete_session(i)
        cleanup_time = time.time() - start_time

        # Should complete within 1 second
        assert cleanup_time < 1.0


class TestNetworkPerformance:
    """Test network performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_telegram_api_response_time(self, mock_telegram_bot):
        """Test Telegram API response time."""
        # Mock Telegram API with realistic response times
        mock_telegram_bot.send_message = AsyncMock()
        mock_telegram_bot.send_photo = AsyncMock()
        mock_telegram_bot.edit_message_text = AsyncMock()

        # Measure API call time
        start_time = time.time()
        await mock_telegram_bot.send_message(chat_id=12345, text="Test message")
        api_time = time.time() - start_time

        # Should complete within 100ms (mocked)
        assert api_time < 0.1

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_api_calls(self, mock_telegram_bot):
        """Test concurrent API calls."""
        async def send_message(chat_id: int, text: str):
            """Send a message."""
            await mock_telegram_bot.send_message(chat_id=chat_id, text=text)

        # Send 50 messages concurrently
        start_time = time.time()
        tasks = []
        for i in range(50):
            task = send_message(i, f"Message {i}")
            tasks.append(task)

        await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Should complete within 1 second
        assert total_time < 1.0


class TestLoadTesting:
    """Test load scenarios."""

    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_high_load_scenario(self, hybrid_storage_with_memory):
        """Test high load scenario."""
        async def simulate_user_session(user_id: int):
            """Simulate a user session."""
            # Create session
            session = SessionState(
                language=Language.ENGLISH,
                theme=Theme.ACQUAINTANCE,
                level=1
            )
            await hybrid_storage_with_memory.save_session(user_id, session)

            # Update session multiple times
            for level in range(1, 4):
                session.level = level
                await hybrid_storage_with_memory.save_session(user_id, session)

            # Retrieve session
            retrieved_session = await hybrid_storage_with_memory.get_session(user_id)
            assert retrieved_session is not None

            # Delete session
            await hybrid_storage_with_memory.delete_session(user_id)

        # Simulate 500 concurrent users
        start_time = time.time()
        user_ids = list(range(500))
        await asyncio.gather(*[
            simulate_user_session(user_id) for user_id in user_ids
        ])
        total_time = time.time() - start_time

        # Should complete within 10 seconds
        assert total_time < 10.0

    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_sustained_load_scenario(self, hybrid_storage_with_memory):
        """Test sustained load scenario."""
        async def sustained_operation():
            """Perform sustained operations."""
            for i in range(100):
                session = SessionState(
                    language=Language.ENGLISH,
                    theme=Theme.ACQUAINTANCE,
                    level=1
                )
                await hybrid_storage_with_memory.save_session(i, session)
                await hybrid_storage_with_memory.get_session(i)
                await hybrid_storage_with_memory.delete_session(i)

        # Run sustained operations for 30 seconds
        start_time = time.time()
        end_time = start_time + 30  # 30 seconds

        tasks = []
        while time.time() < end_time:
            task = asyncio.create_task(sustained_operation())
            tasks.append(task)

            # Limit concurrent tasks
            if len(tasks) >= 10:
                await asyncio.gather(*tasks)
                tasks = []

        # Wait for remaining tasks
        if tasks:
            await asyncio.gather(*tasks)

        # Should complete successfully
        assert time.time() - start_time >= 30


class TestPerformanceMonitoring:
    """Test performance monitoring."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self, mock_metrics):
        """Test performance metrics collection."""
        from vechnost_bot.monitoring import track_performance

        @track_performance("test_operation")
        async def test_operation():
            """Test operation."""
            await asyncio.sleep(0.01)  # 10ms operation
            return "success"

        # Execute operation
        result = await test_operation()

        # Verify metrics were collected
        mock_metrics.increment_counter.assert_called()
        mock_metrics.record_timer.assert_called()

        # Verify result
        assert result == "success"

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_error_metrics_collection(self, mock_metrics):
        """Test error metrics collection."""
        from vechnost_bot.monitoring import track_errors

        @track_errors("test_operation")
        async def failing_operation():
            """Failing operation."""
            raise ValueError("Test error")

        # Execute failing operation
        with pytest.raises(ValueError):
            await failing_operation()

        # Verify error metrics were collected
        mock_metrics.increment_counter.assert_called()

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_operation_context_tracking(self, mock_sentry):
        """Test operation context tracking."""
        from vechnost_bot.monitoring import track_operation

        async with track_operation("test_operation", user_id=12345, theme="acquaintance"):
            await asyncio.sleep(0.01)

        # Verify context was set
        mock_sentry.set_tag.assert_called()
        mock_sentry.set_context.assert_called()


class TestPerformanceBenchmarks:
    """Test performance benchmarks."""

    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_benchmark_session_operations(self, hybrid_storage_with_memory):
        """Benchmark session operations."""
        session = SessionState(
            language=Language.ENGLISH,
            theme=Theme.ACQUAINTANCE,
            level=1
        )

        # Benchmark save operation
        save_times = []
        for _ in range(100):
            start_time = time.time()
            await hybrid_storage_with_memory.save_session(12345, session)
            save_times.append(time.time() - start_time)

        # Benchmark get operation
        get_times = []
        for _ in range(100):
            start_time = time.time()
            await hybrid_storage_with_memory.get_session(12345)
            get_times.append(time.time() - start_time)

        # Calculate statistics
        save_avg = statistics.mean(save_times)
        save_p95 = statistics.quantiles(save_times, n=20)[18]  # 95th percentile
        get_avg = statistics.mean(get_times)
        get_p95 = statistics.quantiles(get_times, n=20)[18]  # 95th percentile

        # Performance requirements
        assert save_avg < 0.05  # Average save under 50ms
        assert save_p95 < 0.1   # 95th percentile save under 100ms
        assert get_avg < 0.02   # Average get under 20ms
        assert get_p95 < 0.05   # 95th percentile get under 50ms

    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_benchmark_callback_processing(self, mock_update, mock_context, hybrid_storage_with_memory):
        """Benchmark callback processing."""
        with patch('vechnost_bot.storage.get_hybrid_storage', return_value=hybrid_storage_with_memory):
            from vechnost_bot.handlers import handle_callback_query

            callback_times = []
            callbacks = [
                "lang_en", "theme_Acquaintance", "level_1",
                "q:acq:1:0", "nav:next", "nav:prev", "back:calendar"
            ]

            for callback_data in callbacks:
                mock_update.callback_query.data = callback_data
                start_time = time.time()
                await handle_callback_query(mock_update, mock_context)
                callback_times.append(time.time() - start_time)

            # Calculate statistics
            avg_time = statistics.mean(callback_times)
            max_time = max(callback_times)
            min_time = min(callback_times)

            # Performance requirements
            assert avg_time < 0.1   # Average under 100ms
            assert max_time < 0.2   # Max under 200ms
            assert min_time < 0.05  # Min under 50ms
