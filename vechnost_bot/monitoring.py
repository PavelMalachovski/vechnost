"""Monitoring and error tracking for the Vechnost bot."""

import asyncio
import logging
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any

import structlog
from sentry_sdk import capture_exception, set_context, set_tag, set_user
from sentry_sdk.integrations.logging import LoggingIntegration

# --------------------------------------------------------------------------
# Logging: one format for every line
# --------------------------------------------------------------------------
#
# Most of the code logs through the standard library, a little through
# structlog, and uvicorn through its own loggers. All of it goes to one
# handler on the root logger whose formatter renders every record the same
# way: JSON with a level, a logger name and a UTC timestamp (or colours in a
# terminal). It used to be `basicConfig(format="%(message)s")`, so a
# standard-library line reached the log with neither level nor time, set
# among structlog's JSON - on Railway an error could not be told from an
# info line.

# The one handler this module puts on the root logger. It is found again by
# its type, so configuring twice (the bot, the web process, a test) never
# stacks a second one.
class StdoutHandler(logging.StreamHandler):
    """A stream handler that writes to whatever `sys.stdout` is right now.

    Not the stream it was created with: a test runner swaps `sys.stdout`
    per test and closes the old one, and a handler holding on to that
    raises on every later line. (The standard library's own last-resort
    handler does the same for stderr.)
    """

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self) -> Any:
        return sys.stdout

    @stream.setter
    def stream(self, value: Any) -> None:
        pass


# The processors every line runs through, whichever door it came in by.
_SHARED_PROCESSORS: list[Any] = [
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
]


def structured_formatter() -> logging.Formatter:
    """The formatter for the root handler (and for uvicorn's log config).

    The timestamp is added here, at the end, rather than in structlog's own
    chain: what reaches Sentry is the event before formatting, and a
    timestamp inside it would make every occurrence of one error a message
    of its own.
    """
    renderer: Any
    if sys.stdout.isatty():
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            # A traceback as one string field: readable in Railway's log
            # viewer, and still greppable for "Traceback" (ci.yml does).
            structlog.processors.format_exc_info,
            renderer,
        ],
    )


# A room, a compatibility test and a «69 ступеней» game are addressed by a
# code in the path, and the code is the key to the seat: whoever reads it
# can sit down in a stranger's game. The two-partner screens poll every few
# seconds, so uvicorn's access log wrote every live code, for every player,
# many times a minute. The first segment after these prefixes is a code
# unless it is one of the fixed routes beside the codes.
_CODE_IN_PATH = re.compile(r"(/api/(?:rooms|compat|steps69)/)([^/?#\s\"]+)")
_NOT_A_CODE = frozenset({"questions", "mine", "pieces"})
# The same codes travel in the Mini App's own address: `?code=` when the bot
# hands a tap on, `tgWebAppStartParam=` when Telegram opens a direct link.
_CODE_IN_QUERY = re.compile(r"([?&](?:code|startapp|start|tgWebAppStartParam)=)[^&#\s\"]*")
CODE_MASK = "***"


def mask_codes(text: str) -> str:
    """`text` with every room, test and game code replaced by `***`."""
    def path(match: re.Match[str]) -> str:
        if match.group(2) in _NOT_A_CODE:
            return match.group(0)
        return match.group(1) + CODE_MASK

    text = _CODE_IN_PATH.sub(path, text)
    return _CODE_IN_QUERY.sub(lambda match: match.group(1) + CODE_MASK, text)


class MaskInviteCodes(logging.Filter):
    """Masks codes in uvicorn's access log, before any handler sees them.

    uvicorn logs a request as a format string with the path among its
    arguments; every string argument is masked, so the filter does not
    depend on where in the line the path sits.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                mask_codes(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.msg, str) and not record.args:
            record.msg = mask_codes(record.msg)
        return True


def uvicorn_log_config(level: str = "INFO") -> dict[str, Any]:
    """The `log_config` uvicorn is started with (`run_webhook.serve_web`).

    uvicorn's own default gives its loggers handlers of their own, in its
    own format, with the access log writing every path as it came. Here its
    loggers keep no handlers and hand their records to the root handler
    above, so its lines look like everyone else's from the first one, and
    the access log passes through `MaskInviteCodes` first.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"mask_codes": {"()": MaskInviteCodes}},
        "formatters": {"structured": {"()": structured_formatter}},
        "handlers": {"stdout": {"()": StdoutHandler, "formatter": "structured"}},
        "loggers": {
            "uvicorn": {"handlers": [], "level": level, "propagate": True},
            "uvicorn.error": {"level": level, "propagate": True},
            "uvicorn.access": {
                "handlers": [], "level": level, "propagate": True, "filters": ["mask_codes"],
            },
        },
        "root": {"handlers": ["stdout"], "level": level},
    }


def _route_uvicorn_through_root() -> None:
    """Make uvicorn's loggers use the root handler, however it was started.

    `run_webhook.serve_web` passes `uvicorn_log_config()`, which already does
    this. A plain `uvicorn ...` on the command line (local development, CI's
    smoke servers) applies uvicorn's default instead, whose handlers would
    print unmasked, unstructured lines; this undoes that once the app starts.
    A logger with no handlers is left as it is: `--no-access-log` switches
    the access log off exactly that way, and must stay off.
    """
    for name in ("uvicorn", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        if uvicorn_logger.handlers:
            uvicorn_logger.handlers.clear()
            uvicorn_logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, MaskInviteCodes) for f in access.filters):
        access.addFilter(MaskInviteCodes())


def configure_logging() -> None:
    """Route every logger in the process through one structured handler."""
    from .config import settings

    # LOG_LEVEL was documented and never read: INFO was hard-coded here.
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            # A DEBUG line under LOG_LEVEL=INFO is dropped before any work.
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            *_SHARED_PROCESSORS,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    handler = next((h for h in root.handlers if isinstance(h, StdoutHandler)), None)
    if handler is None:
        handler = StdoutHandler()
        handler.setFormatter(structured_formatter())
        root.addHandler(handler)
    # On the handler too: a record that propagates up from a logger with a
    # lower level of its own (uvicorn's are INFO) is not stopped by the root
    # logger's level, only by its handlers'.
    handler.setLevel(level)
    root.setLevel(level)

    # httpx logs every Telegram API request at INFO with the full URL,
    # which includes the bot token — keep those out of production logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # APScheduler writes two INFO lines for every job it runs, and the
    # heartbeat runs every minute. A job that fails still logs at ERROR.
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

    _route_uvicorn_through_root()


# Breadcrumbs start at WARNING. At INFO every callback, every /start
# argument and every certificate lookup rode along to Sentry as context on
# the next error, which is how user ids, usernames and gift codes reached a
# third party that was only meant to hold stack traces.
BREADCRUMB_LEVEL = logging.WARNING


def sentry_release() -> str | None:
    """Which build an event came from: the deployed commit.

    Railway sets RAILWAY_GIT_COMMIT_SHA on a deploy from GitHub - the same
    value `/health` reports - so an error in Sentry names the commit it
    happened on and a regression names the deploy that brought it.
    RELEASE_VERSION is for a build that is not a Railway deploy. With
    neither, None lets the SDK look for itself, rather than filing every
    event of every deploy under one release called "unknown".
    """
    return os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("RELEASE_VERSION") or None


def configure_sentry() -> None:
    """Configure Sentry for error tracking and performance monitoring."""
    from .config import settings

    # `settings`, not `os.getenv`: pydantic-settings reads `.env` but does
    # not export it, so a DSN set only there was silently ignored.
    sentry_dsn = settings.sentry_dsn
    if not sentry_dsn:
        return

    # Configure Sentry integrations
    integrations = [
        LoggingIntegration(
            level=BREADCRUMB_LEVEL,    # Capture warnings and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        ),
    ]

    # Initialize Sentry
    import sentry_sdk
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=integrations,
        traces_sample_rate=0.1,  # Capture 10% of transactions for performance monitoring
        environment=settings.environment,
        release=sentry_release(),
        send_default_pii=False,
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
    """Bot metrics and monitoring.

    Every counter and timer is logged at DEBUG. A tap on a card used to
    write about ten INFO lines - the callback, two counters, the render,
    three timers - which buried everything else in the log.
    """

    def __init__(self):
        self.logger = structlog.get_logger("bot_metrics")
        self._counters: dict[str, int] = {}
        self._timers: dict[str, float] = {}

    def increment_counter(self, name: str, value: int = 1, **context) -> None:
        """Increment a counter metric."""
        self._counters[name] = self._counters.get(name, 0) + value
        self.logger.debug("counter_incremented", counter=name, value=value, **context)

    def record_timer(self, name: str, duration: float, **context) -> None:
        """Record a timer metric."""
        self._timers[name] = duration
        self.logger.debug("timer_recorded", timer=name, duration=duration, **context)

    def get_metrics(self) -> dict[str, Any]:
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
            except Exception:
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
            except Exception:
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


def set_user_context(user_id: int, username: str | None = None, **extra_context):
    """Set user context for Sentry and logging.

    The id and nothing else. `username` is still accepted so old call
    sites keep working, and deliberately not forwarded: a Telegram handle
    is a real person's public name, and the error tracker needs a way to
    count affected users, not to name them.
    """
    set_user({"id": str(user_id), **extra_context})

    logger = structlog.get_logger("user_tracking")
    logger.debug("user_context_set", user_id=user_id, **extra_context)


def log_bot_event(event_type: str, **context):
    """Log a bot event with structured data."""
    logger = structlog.get_logger("bot_events")
    logger.info("bot_event", event_type=event_type, **context)

    # Increment counter
    metrics.increment_counter(f"bot_events_{event_type}")


def log_callback_event(callback_data: str | None, user_id: int, **context):
    """Log a callback event with structured data.

    `str | None`, because a callback query is allowed to carry no data at all
    and the caller hands `query.data` straight through. The body already
    guards every use of it; the signature was the only thing claiming
    otherwise.

    DEBUG, like the metrics: one line per tap is a firehose at INFO.
    """
    logger = structlog.get_logger("callback_events")
    logger.debug(
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
    """Log an image rendering event (DEBUG: one per card shown)."""
    logger = structlog.get_logger("image_rendering")
    logger.debug(
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
def get_health_status() -> dict[str, Any]:
    """Get health status for monitoring."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "metrics": metrics.get_metrics(),
        "version": os.getenv("RELEASE_VERSION", "unknown"),
        "environment": os.getenv("ENVIRONMENT", "development"),
    }
