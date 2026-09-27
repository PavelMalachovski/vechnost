"""Stand-ins for uvicorn and the bot, for tests/test_run_webhook.py.

They live in a module of their own because the supervisor starts children
with "spawn": a child imports its target by name, so the target cannot be
defined inside a test or a `python -c` script. Each one writes a marker file
the test waits for, and records how it was stopped.
"""

import os
import signal
import sys
import time
from pathlib import Path


def _ready(marker_dir: str, name: str) -> Path:
    marks = Path(marker_dir)
    (marks / f"{name}.ready").write_text(str(os.getpid()))
    return marks


def sleeper(marker_dir: str, name: str) -> None:
    """Runs until SIGTERM, notes it, and exits cleanly, as uvicorn and run_polling do."""
    marks = Path(marker_dir)

    def on_term(_signum: int, _frame: object) -> None:
        (marks / f"{name}.stopped").write_text("SIGTERM")
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_term)
    _ready(marker_dir, name)
    while True:
        time.sleep(0.1)


def stubborn(marker_dir: str, name: str) -> None:
    """Ignores SIGTERM: only a kill ends it."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    _ready(marker_dir, name)
    while True:
        time.sleep(0.1)


def crasher(marker_dir: str, name: str, code: int) -> None:
    """Dies on its own shortly after starting."""
    _ready(marker_dir, name)
    time.sleep(0.5)
    sys.exit(code)
