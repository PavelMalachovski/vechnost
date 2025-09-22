"""Tests for monitoring and error tracking."""

import os
import pytest
import time
from unittest.mock import MagicMock, patch

from vechnost_bot.monitoring import (
    BotMetrics,
    get_health_status,
    initialize_monitoring,
    log_bot_event,
    log_callback_event,
    log_image_rendering_event,
    log_session_event,
    set_user_context,
    track_operation,
    track_performance,
    track_errors,
)


class TestBotMetrics:
    """Test BotMetrics class."""

    def test_increment_counter(self):
        """Test incrementing counter metrics."""
        metrics = BotMetrics()

        metrics.increment_counter("test_counter", 5)
        metrics.increment_counter("test_counter", 3)

        assert metrics._counters["test_counter"] == 8

    def test_record_timer(self):
        """Test recording timer metrics."""
        metrics = BotMetrics()

        metrics.record_timer("test_timer", 1.5)

        assert metrics._timers["test_timer"] == 1.5

    def test_get_metrics(self):
        """Test getting current metrics."""
        metrics = BotMetrics()

        metrics.increment_counter("test_counter", 5)
        metrics.record_timer("test_timer", 1.5)

        result = metrics.get_metrics()

        assert result["counters"]["test_counter"] == 5
        assert result["timers"]["test_timer"] == 1.5


class TestTrackPerformance:
    """Test track_performance decorator."""

    def test_sync_function_success(self):
        """Test tracking performance of successful sync function."""
        @track_performance("test_operation")
        def test_func():
            time.sleep(0.01)
            return "success"

        result = test_func()

        assert result == "success"

    def test_sync_function_error(self):
        """Test tracking performance of sync function that raises error."""
        @track_performance("test_operation")
        def test_func():
            time.sleep(0.01)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            test_func()

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test tracking performance of successful async function."""
        @track_performance("test_operation")
        async def test_func():
            await asyncio.sleep(0.01)
            return "success"

        result = await test_func()

        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_function_error(self):
        """Test tracking performance of async function that raises error."""
        @track_performance("test_operation")
        async def test_func():
            await asyncio.sleep(0.01)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await test_func()


class TestTrackErrors:
    """Test track_errors decorator."""

    def test_sync_function_success(self):
        """Test tracking errors of successful sync function."""
        @track_errors("test_operation")
        def test_func():
            return "success"

        result = test_func()

        assert result == "success"

    def test_sync_function_error(self):
        """Test tracking errors of sync function that raises error."""
        @track_errors("test_operation")
        def test_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            test_func()

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test tracking errors of successful async function."""
        @track_errors("test_operation")
        async def test_func():
            return "success"

        result = await test_func()

        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_function_error(self):
        """Test tracking errors of async function that raises error."""
        @track_errors("test_operation")
        async def test_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await test_func()


class TestTrackOperation:
    """Test track_operation context manager."""

    @pytest.mark.asyncio
    async def test_successful_operation(self):
        """Test tracking successful operation."""
        async with track_operation("test_operation", user_id=123):
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_failed_operation(self):
        """Test tracking failed operation."""
        with pytest.raises(ValueError):
            async with track_operation("test_operation", user_id=123):
                await asyncio.sleep(0.01)
                raise ValueError("Test error")


class TestLoggingFunctions:
    """Test logging functions."""

    def test_log_bot_event(self):
        """Test logging bot event."""
        with patch('vechnost_bot.monitoring.metrics') as mock_metrics:
            log_bot_event("test_event", user_id=123, action="test")

            mock_metrics.increment_counter.assert_called_with("bot_events_test_event")

    def test_log_callback_event(self):
        """Test logging callback event."""
        with patch('vechnost_bot.monitoring.metrics') as mock_metrics:
            log_callback_event("theme_Acquaintance", 123, action="test")

            # Check that both calls were made
            assert mock_metrics.increment_counter.call_count >= 2
            calls = mock_metrics.increment_counter.call_args_list
            call_args = [call[0][0] for call in calls]
            assert "callback_events_total" in call_args
            assert "callback_events_theme" in call_args

    def test_log_image_rendering_event_success(self):
        """Test logging successful image rendering event."""
        with patch('vechnost_bot.monitoring.metrics') as mock_metrics:
            log_image_rendering_event(True, 1.5, user_id=123)

            mock_metrics.increment_counter.assert_called_with("image_rendering_success")
            mock_metrics.record_timer.assert_called_with("image_rendering_success_duration", 1.5)

    def test_log_image_rendering_event_failure(self):
        """Test logging failed image rendering event."""
        with patch('vechnost_bot.monitoring.metrics') as mock_metrics:
            log_image_rendering_event(False, 0.5, user_id=123)

            mock_metrics.increment_counter.assert_called_with("image_rendering_failed")
            mock_metrics.record_timer.assert_called_with("image_rendering_failed_duration", 0.5)

    def test_log_session_event(self):
        """Test logging session event."""
        with patch('vechnost_bot.monitoring.metrics') as mock_metrics:
            log_session_event("created", 123, theme="Acquaintance")

            mock_metrics.increment_counter.assert_called_with("session_events_created")


class TestSetUserContext:
    """Test set_user_context function."""

    def test_set_user_context(self):
        """Test setting user context."""
        with patch('vechnost_bot.monitoring.set_user') as mock_set_user:
            set_user_context(123, "testuser", theme="Acquaintance")

            mock_set_user.assert_called_once_with({
                "id": "123",
                "username": "testuser",
                "theme": "Acquaintance"
            })


class TestGetHealthStatus:
    """Test get_health_status function."""

    def test_get_health_status(self):
        """Test getting health status."""
        with patch.dict(os.environ, {"RELEASE_VERSION": "1.0.0", "ENVIRONMENT": "test"}):
            status = get_health_status()

            assert status["status"] == "healthy"
            assert status["version"] == "1.0.0"
            assert status["environment"] == "test"
            assert "timestamp" in status
            assert "metrics" in status


class TestInitializeMonitoring:
    """Test initialize_monitoring function."""

    def test_initialize_monitoring(self):
        """Test initializing monitoring."""
        with patch('vechnost_bot.monitoring.configure_logging') as mock_configure_logging:
            with patch('vechnost_bot.monitoring.configure_sentry') as mock_configure_sentry:
                initialize_monitoring()

                mock_configure_logging.assert_called_once()
                mock_configure_sentry.assert_called_once()


class TestSentryIntegration:
    """Test Sentry integration."""

    def test_configure_sentry_with_dsn(self):
        """Test configuring Sentry with DSN."""
        with patch.dict(os.environ, {"SENTRY_DSN": "https://test@sentry.io/123"}):
            with patch('sentry_sdk.init') as mock_init:
                from vechnost_bot.monitoring import configure_sentry
                configure_sentry()

                mock_init.assert_called_once()

    def test_configure_sentry_without_dsn(self):
        """Test configuring Sentry without DSN."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('sentry_sdk.init') as mock_init:
                from vechnost_bot.monitoring import configure_sentry
                configure_sentry()

                mock_init.assert_not_called()


# Import asyncio for async tests
import asyncio
