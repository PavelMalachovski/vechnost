"""Monitoring and error tracking for the Vechnost bot."""

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Dict, Optional

import structlog
from sentry_sdk import capture_exception, capture_message, set_context, set_tag, set_user
from sentry_sdk.integrations.logging import LoggingIntegration

# Configure structlog
def configure_logging() -> None:
    """Configure structured logging with structlog."""
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    # Configure structlog
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if sys.stderr.isatty():
        # Pretty printing when we run in a terminal session
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # JSON output for production
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def configure_sentry() -> None:
    """Configure Sentry for error tracking and performance monitoring."""
    sentry_dsn = os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        return

    # Configure Sentry integrations
    integrations = [
        LoggingIntegration(
            level=logging.INFO,        # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        ),
    ]

    # Initialize Sentry
    import sentry_sdk
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=integrations,
        traces_sample_rate=0.1,  # Capture 10% of transactions for performance monitoring
        environment=os.getenv("ENVIRONMENT", "development"),
        release=os.getenv("RELEASE_VERSION", "unknown"),
        before_send=before_send_filter,
    )


def before_send_filter(event, hint):
    """Filter events before sending to Sentry."""
    # Don't send certain types of errors
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        if exc_type.__name__ in ['KeyboardInterrupt', 'SystemExit']:
            return None

    # Add custom context
    event.setdefault('tags', {})
    event['tags']['bot_name'] = 'vechnost-bot'

    return event


class BotMetrics:
    """Bot metrics and monitoring."""

    def __init__(self):
        self.logger = structlog.get_logger("bot_metrics")
        self._counters: Dict[str, int] = {}
        self._timers: Dict[str, float] = {}

    def increment_counter(self, name: str, value: int = 1, **context) -> None:
        """Increment a counter metric."""
        self._counters[name] = self._counters.get(name, 0) + value
        self.logger.info("counter_incremented", counter=name, value=value, **context)

    def record_timer(self, name: str, duration: float, **context) -> None:
        """Record a timer metric."""
        self._timers[name] = duration
        self.logger.info("timer_recorded", timer=name, duration=duration, **context)

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return {
            "counters": self._counters.copy(),
            "timers": self._timers.copy(),
        }


# Global metrics instance
metrics = BotMetrics()


def track_performance(operation_name: str):
    """Decorator to track performance of operations."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                metrics.record_timer(f"{operation_name}_success", duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics.record_timer(f"{operation_name}_error", duration)
                metrics.increment_counter(f"{operation_name}_errors")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                metrics.record_timer(f"{operation_name}_success", duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics.record_timer(f"{operation_name}_error", duration)
                metrics.increment_counter(f"{operation_name}_errors")
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator


def track_errors(operation_name: str):
    """Decorator to track errors and send them to Sentry."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Set context for Sentry
                set_tag("operation", operation_name)
                set_context("operation_context", {
                    "function": func.__name__,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                })

                # Capture exception
                capture_exception(e)

                # Log error
                logger = structlog.get_logger("error_tracking")
                logger.error(
                    "operation_failed",
                    operation=operation_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True
                )

                # Increment error counter
                metrics.increment_counter(f"{operation_name}_errors")

                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Set context for Sentry
                set_tag("operation", operation_name)
                set_context("operation_context", {
                    "function": func.__name__,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                })

                # Capture exception
                capture_exception(e)

                # Log error
                logger = structlog.get_logger("error_tracking")
                logger.error(
                    "operation_failed",
                    operation=operation_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True
                )

                # Increment error counter
                metrics.increment_counter(f"{operation_name}_errors")

                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator


@asynccontextmanager
async def track_operation(operation_name: str, **context):
    """Context manager to track operations."""
    logger = structlog.get_logger("operation_tracking")
    start_time = time.time()

    logger.info("operation_started", operation=operation_name, **context)
    metrics.increment_counter(f"{operation_name}_started")

    try:
        yield
        duration = time.time() - start_time
        logger.info("operation_completed", operation=operation_name, duration=duration, **context)
        metrics.record_timer(f"{operation_name}_success", duration)
        metrics.increment_counter(f"{operation_name}_completed")
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            "operation_failed",
            operation=operation_name,
            duration=duration,
            error=str(e),
            error_type=type(e).__name__,
            **context,
            exc_info=True
        )
        metrics.record_timer(f"{operation_name}_error", duration)
        metrics.increment_counter(f"{operation_name}_failed")

        # Send to Sentry
        set_tag("operation", operation_name)
        set_context("operation_context", context)
        capture_exception(e)

        raise


def set_user_context(user_id: int, username: Optional[str] = None, **extra_context):
    """Set user context for Sentry and logging."""
    set_user({
        "id": str(user_id),
        "username": username,
        **extra_context
    })

    logger = structlog.get_logger("user_tracking")
    logger.info("user_context_set", user_id=user_id, username=username, **extra_context)


def log_bot_event(event_type: str, **context):
    """Log a bot event with structured data."""
    logger = structlog.get_logger("bot_events")
    logger.info("bot_event", event_type=event_type, **context)

    # Increment counter
    metrics.increment_counter(f"bot_events_{event_type}")


def log_callback_event(callback_data: str, user_id: int, **context):
    """Log a callback event with structured data."""
    logger = structlog.get_logger("callback_events")
    logger.info(
        "callback_event",
        callback_data=callback_data,
        user_id=user_id,
        **context
    )

    # Increment counter
    metrics.increment_counter("callback_events_total")

    # Track callback type
    if callback_data and callback_data.startswith("theme_"):
        metrics.increment_counter("callback_events_theme")
    elif callback_data and callback_data.startswith("level_"):
        metrics.increment_counter("callback_events_level")
    elif callback_data and callback_data.startswith("cal:"):
        metrics.increment_counter("callback_events_calendar")
    elif callback_data and callback_data.startswith("q:"):
        metrics.increment_counter("callback_events_question")
    elif callback_data and callback_data.startswith("nav:"):
        metrics.increment_counter("callback_events_navigation")
    elif callback_data and callback_data.startswith("toggle:"):
        metrics.increment_counter("callback_events_toggle")
    elif callback_data and callback_data.startswith("back:"):
        metrics.increment_counter("callback_events_back")
    else:
        metrics.increment_counter("callback_events_other")


def log_image_rendering_event(success: bool, duration: float, **context):
    """Log an image rendering event."""
    logger = structlog.get_logger("image_rendering")
    logger.info(
        "image_rendering_event",
        success=success,
        duration=duration,
        **context
    )

    if success:
        metrics.increment_counter("image_rendering_success")
        metrics.record_timer("image_rendering_success_duration", duration)
    else:
        metrics.increment_counter("image_rendering_failed")
        metrics.record_timer("image_rendering_failed_duration", duration)


def log_session_event(event_type: str, user_id: int, **context):
    """Log a session event."""
    logger = structlog.get_logger("session_events")
    logger.info(
        "session_event",
        event_type=event_type,
        user_id=user_id,
        **context
    )

    metrics.increment_counter(f"session_events_{event_type}")


# Initialize monitoring
def initialize_monitoring() -> None:
    """Initialize monitoring and error tracking."""
    configure_logging()
    configure_sentry()

    logger = structlog.get_logger("monitoring")
    logger.info("monitoring_initialized")


# Health check endpoint
def get_health_status() -> Dict[str, Any]:
    """Get health status for monitoring."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "metrics": metrics.get_metrics(),
        "version": os.getenv("RELEASE_VERSION", "unknown"),
        "environment": os.getenv("ENVIRONMENT", "development"),
    }
