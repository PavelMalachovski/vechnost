"""Comprehensive performance tests for Vechnost bot."""

import asyncio
import statistics
import time
import tracemalloc
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vechnost_bot.models import ContentType, Language, SessionState, Theme
from vechnost_bot.renderer import render_card


class TestStoragePerformance:
    """Test storage performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_save_performance(self, hybrid_storage_with_memory):
        """Test session save performance."""
        session = SessionState(
            language=Language.RUSSIAN,
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
            language=Language.RUSSIAN,
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
                language=Language.RUSSIAN,
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
            assert session.language == Language.RUSSIAN
            assert session.theme == Theme.ACQUAINTANCE

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_update_performance(self, hybrid_storage_with_memory):
        """Test session update performance."""
        session = SessionState(
            language=Language.RUSSIAN,
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
        """A thousand live sessions must not cost more than a few megabytes.

        Measured with `tracemalloc`, which reports what this block allocated,
        not with the process RSS the earlier version read: RSS moves with the
        allocator's arenas and with whatever every other test in the run left
        behind, so a 50MB bound on it passed no matter what the storage did.
        """
        tracemalloc.start()
        try:
            before = tracemalloc.get_traced_memory()[0]

            sessions = []
            for i in range(1000):
                session = SessionState(
                    language=Language.RUSSIAN,
                    theme=Theme.ACQUAINTANCE,
                    level=1,
                )
                await hybrid_storage_with_memory.save_session(i, session)
                sessions.append(await hybrid_storage_with_memory.get_session(i))

            after = tracemalloc.get_traced_memory()[0]
        finally:
            tracemalloc.stop()

        assert len(sessions) == 1000
        assert all(session is not None for session in sessions)
        # ~2KB per session leaves room for the pydantic model and the dict
        # entry, and still catches a session that starts carrying a deck.
        assert after - before < 1000 * 2048


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
        with patch('vechnost_bot.storage.get_redis_storage', return_value=hybrid_storage_with_memory):
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
        with patch('vechnost_bot.storage.get_redis_storage', return_value=hybrid_storage_with_memory):
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
        with patch('vechnost_bot.storage.get_redis_storage', return_value=hybrid_storage_with_memory):
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
    """Test image rendering performance.

    Against the real renderer. The earlier version of this class patched
    `render_card` with a mock and then timed the mock, so it asserted that
    returning a constant takes under half a second and would have passed with
    the renderer entirely broken - which is how it survived losing the
    `PIL` attribute it also patched.
    """

    BACKGROUND = "assets/backgrounds/acq/acq_1.png"

    @pytest.mark.performance
    def test_question_card_rendering_performance(self):
        """A card is drawn while the player is watching a spinner."""
        # Warm the font and background caches first: the first render of the
        # process pays for loading four TrueType faces, and a player only
        # ever waits for the second one onward.
        render_card("Разогрев", self.BACKGROUND)

        start_time = time.time()
        image_data = render_card(
            "Что тебя удивило в нас за последний год?", self.BACKGROUND
        )
        render_time = time.time() - start_time

        assert render_time < 0.5
        payload = image_data.getvalue()
        # JPEG at quality 92, not PNG: `renderer.py` composites onto
        # photographic backgrounds, where PNG would triple the bytes a phone
        # on a train has to pull down for no visible gain.
        assert payload.startswith(b"\xff\xd8\xff"), "a card is a JPEG"
        assert len(payload) > 10_000

    @pytest.mark.performance
    def test_a_long_question_still_renders_in_time(self):
        """The slowest card is the one that needs the most line-breaking."""
        render_card("Разогрев", self.BACKGROUND)

        start_time = time.time()
        render_card(
            "Расскажи о моменте, когда ты понял, что доверяешь мне полностью, "
            "и о том, что этому предшествовало, во всех подробностях, "
            "которые ты помнишь.",
            self.BACKGROUND,
            footer="Знакомство · 12/50",
            watermark="VECHNOST",
        )
        render_time = time.time() - start_time

        assert render_time < 1.0

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_image_rendering(self):
        """Twenty cards at once, as a busy evening would ask for them.

        `render_card` is synchronous, so this measures the thread pool the
        event loop hands it to - which is what actually happens when twenty
        chats press a button in the same second.
        """
        render_card("Разогрев", self.BACKGROUND)

        start_time = time.time()
        images = await asyncio.gather(*[
            asyncio.to_thread(render_card, f"Вопрос {i}", self.BACKGROUND)
            for i in range(20)
        ])
        total_time = time.time() - start_time

        assert total_time < 5.0
        assert len(images) == 20
        assert all(image.getvalue().startswith(b"\xff\xd8\xff") for image in images)


class TestMemoryPerformance:
    """Test memory performance."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_session_memory_usage(self, hybrid_storage_with_memory):
        """Cost per stored session stays flat as the store fills up.

        The earlier version measured process RSS and "cleared" between rounds
        by deleting one chat id out of a thousand, so every round measured the
        previous round's sessions as well and the bound it asserted was on the
        whole process rather than on the store.
        """
        store = hybrid_storage_with_memory.memory_storage
        per_session = []

        for count in (100, 200, 400, 800):
            store.sessions.clear()
            tracemalloc.start()
            try:
                before = tracemalloc.get_traced_memory()[0]
                for i in range(count):
                    await hybrid_storage_with_memory.save_session(
                        i,
                        SessionState(
                            language=Language.RUSSIAN,
                            theme=Theme.ACQUAINTANCE,
                            level=1,
                        ),
                    )
                after = tracemalloc.get_traced_memory()[0]
            finally:
                tracemalloc.stop()

            assert len(store.sessions) == count
            per_session.append((after - before) / count)

        # Flat, not merely bounded: doubling the count four times must not
        # make each session more expensive, which is what a store that keeps
        # a copy of everything it has ever held would do.
        assert max(per_session) < 2 * min(per_session)

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_deleted_sessions_are_released(self, hybrid_storage_with_memory):
        """Deleting a session removes it, rather than tombstoning it."""
        store = hybrid_storage_with_memory.memory_storage
        store.sessions.clear()

        for i in range(500):
            await hybrid_storage_with_memory.save_session(i, SessionState())
        assert len(store.sessions) == 500

        for i in range(500):
            await hybrid_storage_with_memory.delete_session(i)

        assert store.sessions == {}

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_memory_cleanup_performance(self, hybrid_storage_with_memory):
        """Test memory cleanup performance."""
        # Create many sessions
        for i in range(1000):
            session = SessionState(
                language=Language.RUSSIAN,
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
                language=Language.RUSSIAN,
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
                    language=Language.RUSSIAN,
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
        """A tracked operation records a timer and a counter."""
        from vechnost_bot.monitoring import track_performance

        @track_performance("test_operation")
        async def test_operation():
            """Test operation."""
            await asyncio.sleep(0.01)  # 10ms operation
            return "success"

        result = await test_operation()

        assert result == "success"
        mock_metrics.record_timer.assert_called_once()
        timer_name, duration = mock_metrics.record_timer.call_args.args
        assert timer_name == "test_operation_success"
        assert duration >= 0.01, "the timer must measure the operation"

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_error_metrics_collection(self, mock_metrics):
        """A failure is counted under the operation that failed."""
        from vechnost_bot.monitoring import track_errors

        @track_errors("test_operation")
        async def failing_operation():
            """Failing operation."""
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_operation()

        mock_metrics.increment_counter.assert_called_once_with(
            "test_operation_errors"
        )

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_operation_context_tracking(self, mock_sentry, mock_metrics):
        """Sentry gets the operation's context - on the path that needs it.

        `track_operation` tags Sentry only when the block raises, which is the
        only time there is an exception for the tags to be attached to. The
        earlier version ran a successful block and asserted `set_tag` had been
        called, on a MagicMock that was never wired into the module: it could
        not have passed even with the tagging working.
        """
        from vechnost_bot.monitoring import track_operation

        with pytest.raises(ValueError):
            async with track_operation(
                "test_operation", user_id=12345, theme="acquaintance"
            ):
                raise ValueError("Test error")

        mock_sentry["set_tag"].assert_called_once_with("operation", "test_operation")
        mock_sentry["set_context"].assert_called_once_with(
            "operation_context", {"user_id": 12345, "theme": "acquaintance"}
        )
        mock_sentry["capture_exception"].assert_called_once()

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_a_successful_operation_does_not_page_sentry(
        self, mock_sentry, mock_metrics
    ):
        """Nothing went wrong, so nothing is reported."""
        from vechnost_bot.monitoring import track_operation

        async with track_operation("test_operation", user_id=12345):
            await asyncio.sleep(0.01)

        mock_sentry["capture_exception"].assert_not_called()
        mock_metrics.increment_counter.assert_any_call("test_operation_completed")


class TestPerformanceBenchmarks:
    """Test performance benchmarks."""

    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_benchmark_session_operations(self, hybrid_storage_with_memory):
        """Benchmark session operations."""
        session = SessionState(
            language=Language.RUSSIAN,
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
        with patch('vechnost_bot.storage.get_redis_storage', return_value=hybrid_storage_with_memory):
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
