"""What the log looks like: one format, with a level and a time, and no codes.

`basicConfig(format="%(message)s")` printed every standard-library record
- most of the code logs that way - with neither level nor time, set among
structlog's JSON, so on Railway an error could not be told from an info
line. uvicorn's access log wrote every path as it came, and the two-partner
screens poll: every live room, test and game code, for every player, many
times a minute - and a code is a seat in a stranger's game. And one tap on a
card wrote about ten INFO lines.
"""

import json
import logging
import logging.config
from unittest.mock import patch

import pytest
import structlog

from vechnost_bot import monitoring
from vechnost_bot.config import settings

CODE = "ABCDEFGHJKLMNPQR"


@pytest.fixture
def log_output(capsys):
    """What the process prints, with logging put back afterwards.

    The handler writes to whatever `sys.stdout` is when a line is logged, so
    `capsys` sees exactly what Railway would. Configuring logging is
    process-wide, and so is dictConfig: everything it touches is restored,
    so no other test inherits a handler or a level.
    """
    root = logging.getLogger()
    touched = [
        logging.getLogger(name)
        for name in (
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "apscheduler.executors.default",
        )
    ]
    saved_root = (root.handlers[:], root.level)
    saved = [(lg, lg.handlers[:], lg.level, lg.propagate, lg.filters[:]) for lg in touched]
    # Start from no handler of ours, so the formatter is built for the
    # captured stream (not a terminal) and nothing configured earlier leaks in.
    root.handlers[:] = [h for h in root.handlers if not isinstance(h, monitoring.StdoutHandler)]
    try:
        yield capsys
    finally:
        root.handlers[:], level = saved_root
        root.setLevel(level)
        for lg, handlers, lvl, propagate, filters in saved:
            lg.handlers[:] = handlers
            lg.setLevel(lvl)
            lg.propagate = propagate
            lg.filters[:] = filters
        structlog.reset_defaults()


def _lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


def _access(path: str) -> None:
    """A request line exactly as uvicorn's access logger writes it."""
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "203.0.113.7:51234", "GET", path, "1.1", 200
    )


def test_every_line_has_a_level_a_logger_and_a_time(log_output):
    monitoring.configure_logging()

    logging.getLogger("vechnost_bot.payments.web").warning("a stdlib line %s", "with args")
    structlog.get_logger("bot_events").info("bot_event", event_type="start_command")
    try:
        raise ZeroDivisionError("boom")
    except ZeroDivisionError:
        logging.getLogger("vechnost_bot.handlers").exception("it failed")

    stdlib, structured, failure = _lines(log_output)
    for line in (stdlib, structured, failure):
        assert {"event", "level", "logger", "timestamp"} <= line.keys(), line
    assert stdlib["event"] == "a stdlib line with args"
    assert stdlib["level"] == "warning"
    assert structured["event_type"] == "start_command"
    # A traceback stays one greppable field: CI's smoke looks for "Traceback".
    assert failure["level"] == "error"
    assert failure["exception"].startswith("Traceback")


def test_configuring_twice_does_not_print_twice(log_output):
    monitoring.configure_logging()
    monitoring.configure_logging()

    logging.getLogger("vechnost_bot").warning("once")

    assert [line["event"] for line in _lines(log_output)] == ["once"]
    assert sum(isinstance(h, monitoring.StdoutHandler) for h in logging.getLogger().handlers) == 1


@pytest.mark.parametrize(
    "path",
    [
        f"/api/rooms/{CODE}",
        f"/api/rooms/{CODE}/join",
        f"/api/rooms/{CODE}/advance",
        f"/api/compat/{CODE}",
        f"/api/compat/{CODE}/answer",
        f"/api/compat/{CODE}/result?lang=ru",
        f"/api/steps69/{CODE}/board",
        f"/api/steps69/{CODE}/roll",
        "/api/steps69/ABCDEF",  # a legacy six-character code
        f"/app/?screen=coop&code={CODE}",
        f"/app/?tgWebAppStartParam=duo_{CODE}",
    ],
)
def test_a_code_never_reaches_the_access_log(log_output, path):
    monitoring.configure_logging()

    _access(path)

    (line,) = _lines(log_output)
    assert CODE not in line["event"] and "ABCDEF " not in line["event"]
    assert monitoring.CODE_MASK in line["event"]
    assert '"GET ' in line["event"] and line["event"].endswith(" 200")


@pytest.mark.parametrize(
    "path",
    [
        "/api/compat/questions?lang=ru",
        "/api/compat/mine",
        "/api/steps69/pieces",
        "/api/steps69/mine",
        "/api/rooms",
        "/api/library/dates?nsfw=1",
        "/health",
    ],
)
def test_the_routes_beside_the_codes_are_left_readable(log_output, path):
    monitoring.configure_logging()

    _access(path)

    (line,) = _lines(log_output)
    assert path in line["event"]


def test_uvicorn_started_with_the_log_config_is_masked_from_its_first_line(log_output):
    """`run_webhook.serve_web` hands uvicorn this config, so even the lines
    uvicorn writes before the app has started are in the app's format."""
    logging.config.dictConfig(monitoring.uvicorn_log_config())

    logging.getLogger("uvicorn.error").info("Started server process [%d]", 7)
    _access(f"/api/rooms/{CODE}/advance")

    started, request = _lines(log_output)
    assert started["event"] == "Started server process [7]"
    assert started["level"] == "info" and "timestamp" in started
    assert request["event"].count(monitoring.CODE_MASK) == 1
    assert CODE not in request["event"]


def test_a_plain_uvicorn_start_is_brought_into_line(log_output):
    """`uvicorn ...` on the command line applies uvicorn's own default: its
    loggers get handlers of their own, printing paths as they came. The app
    takes them over when it starts, whoever launched it."""
    from uvicorn.config import LOGGING_CONFIG

    logging.config.dictConfig(LOGGING_CONFIG)
    monitoring.configure_logging()

    access = logging.getLogger("uvicorn.access")
    assert access.handlers == [] and access.propagate
    _access(f"/api/compat/{CODE}")

    (line,) = _lines(log_output)
    assert CODE not in line["event"]


def test_an_access_log_switched_off_stays_off(log_output):
    """`--no-access-log` leaves the logger without handlers and without
    propagation; taking it over would switch it back on."""
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False

    monitoring.configure_logging()
    _access("/health")

    assert access.propagate is False
    assert _lines(log_output) == []


def test_serve_web_starts_uvicorn_with_the_log_config():
    from vechnost_bot import run_webhook

    with patch("uvicorn.run") as run:
        run_webhook.serve_web(8123)

    assert run.call_args.kwargs["port"] == 8123
    assert run.call_args.kwargs["log_config"] == monitoring.uvicorn_log_config()


def test_a_tap_on_a_card_writes_no_info_line(log_output):
    """The callback, its counters, the render and its timers: DEBUG, all of it."""
    monitoring.configure_logging()

    @monitoring.track_performance("callback_query")
    def handle() -> str:
        return "ok"

    handle()
    monitoring.log_callback_event("q:acq:1:0", 12345)
    monitoring.log_image_rendering_event(True, 0.02)
    monitoring.set_user_context(12345)

    assert _lines(log_output) == []


def test_log_level_holds_for_uvicorn_too(log_output):
    """A record from a logger with a lower level of its own (uvicorn's are
    INFO) is not stopped by the root logger's level, only by its handler's."""
    with patch.object(settings, "log_level", "WARNING"):
        monitoring.configure_logging()
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    _access("/health")
    logging.getLogger("vechnost_bot").warning("still here")

    assert [line["event"] for line in _lines(log_output)] == ["still here"]


def test_the_scheduler_does_not_log_every_heartbeat(log_output):
    monitoring.configure_logging()

    logging.getLogger("apscheduler.executors.default").info('Running job "heartbeat"')

    assert _lines(log_output) == []


def test_what_reaches_sentry_is_the_same_for_the_same_error(log_output):
    """Sentry groups a log message by its text. A timestamp inside it made
    every occurrence of one error an issue of its own."""
    monitoring.configure_logging()
    seen: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record)

    keep = Keep()
    logging.getLogger().addHandler(keep)
    try:
        for _ in range(2):
            structlog.get_logger("vechnost_bot.redis").error("Redis unavailable", attempt=1)
    finally:
        logging.getLogger().removeHandler(keep)

    first, second = (record.getMessage() for record in seen)
    assert first == second
    assert "Redis unavailable" in first
