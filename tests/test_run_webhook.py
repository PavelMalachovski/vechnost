"""The supervisor production starts: `python -m vechnost_bot.run_webhook`.

It used to have no tests at all and no SIGTERM handler: a redeploy's SIGTERM
reached a PID 1 that ignored it, and both children were killed mid-request
when the grace period ran out. These run the real supervisor in a subprocess
with stand-in children (tests/supervisor_targets.py) and signal it the way
the platform does.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import vechnost_bot.run_webhook as run_webhook

# Real processes and a real stop timeout: seconds, by design.
pytestmark = pytest.mark.slow

REPO = Path(__file__).parent.parent


def _start(children: str) -> subprocess.Popen:
    script = (
        "import sys\n"
        "from vechnost_bot.run_webhook import supervise\n"
        "from tests.supervisor_targets import crasher, sleeper, stubborn\n"
        f"sys.exit(supervise({children}, stop_timeout=2, poll_interval=0.1))\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_for(marks: Path, *names: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while not all((marks / name).exists() for name in names):
        assert time.monotonic() < deadline, f"children never started: {sorted(os.listdir(marks))}"
        time.sleep(0.05)


def _alive(marks: Path, name: str) -> bool:
    pid = int((marks / f"{name}.ready").read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_sigterm_stops_both_children_and_exits_cleanly(tmp_path: Path) -> None:
    d = str(tmp_path)
    supervisor = _start(f"[('web', sleeper, ({d!r}, 'web')), ('bot', sleeper, ({d!r}, 'bot'))]")
    _wait_for(tmp_path, "web.ready", "bot.ready")

    supervisor.send_signal(signal.SIGTERM)
    out, _ = supervisor.communicate(timeout=30)

    assert supervisor.returncode == 0, out
    assert (tmp_path / "web.stopped").exists(), f"the web child was not asked to stop\n{out}"
    assert (tmp_path / "bot.stopped").exists(), f"the bot was not asked to stop\n{out}"
    assert not _alive(tmp_path, "web") and not _alive(tmp_path, "bot"), "a child outlived it"


def test_a_child_that_dies_takes_the_other_down(tmp_path: Path) -> None:
    """A dead bot behind a healthy web server must not run on unnoticed."""
    d = str(tmp_path)
    supervisor = _start(f"[('web', sleeper, ({d!r}, 'web')), ('bot', crasher, ({d!r}, 'bot', 3))]")
    out, _ = supervisor.communicate(timeout=30)

    assert supervisor.returncode == 3, out
    assert (tmp_path / "web.stopped").exists(), out
    assert not _alive(tmp_path, "web")


def test_a_child_that_ignores_sigterm_is_killed_after_the_timeout(tmp_path: Path) -> None:
    d = str(tmp_path)
    supervisor = _start(f"[('web', sleeper, ({d!r}, 'web')), ('bot', stubborn, ({d!r}, 'bot'))]")
    _wait_for(tmp_path, "web.ready", "bot.ready")

    started = time.monotonic()
    supervisor.send_signal(signal.SIGTERM)
    out, _ = supervisor.communicate(timeout=30)

    assert supervisor.returncode == 0, out
    assert "did not stop in time" in out
    assert not _alive(tmp_path, "bot")
    assert time.monotonic() - started < 15, "it waited far past its own timeout"


def test_production_runs_the_web_server_and_the_bot(monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(run_webhook, "supervise", lambda children, **_: seen.extend(children) or 0)
    monkeypatch.setenv("PORT", "8123")

    assert run_webhook.main() == 0
    assert [(name, target, args) for name, target, args in seen] == [
        ("webhook server", run_webhook.serve_web, (8123,)),
        ("bot", run_webhook.serve_bot, ()),
    ]
