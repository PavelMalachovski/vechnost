#!/usr/bin/env python3
"""Run the web server and the Telegram bot side by side, as production does.

Railway starts one process, `python -m vechnost_bot.run_webhook`, and this
is it: the FastAPI app (Mini App, API, Tribute webhooks) and the bot run as
two child processes under a small supervisor.

- If either child dies, the supervisor stops the other and exits non-zero,
  so the platform's restart policy brings the pair back together. Joining
  them one after the other used to leave the deployment running half-alive:
  a dead bot behind a healthy web server, invisibly.
- On SIGTERM or SIGINT (a redeploy, a stop) it passes SIGTERM on and waits
  for both to finish: uvicorn drains its requests, and the bot's
  run_polling stops cleanly and confirms the updates it has handled. It used
  to ignore SIGTERM - as PID 1 in a container nothing handled it - so the
  platform killed both children mid-request at the end of its grace period,
  and the bot handled its last updates a second time after the restart.

The children are started with the "spawn" method and their targets live at
module level, so the supervisor does not depend on `fork`, which newer
Pythons no longer use by default.
"""

import multiprocessing
import os
import signal
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

# How long the children get to finish after SIGTERM before they are killed.
STOP_TIMEOUT = 20.0
# How often the supervisor looks at its children.
POLL_INTERVAL = 0.5
# The bot starts a moment after the web process, which creates the tables
# first; both would otherwise run the startup steps at once on a fresh
# database.
BOT_START_DELAY = 3.0

Child = tuple[str, Callable[..., Any], tuple[Any, ...]]


def serve_web(port: int) -> None:
    """The web process: FastAPI under uvicorn, logging in the app's format.

    The log config routes uvicorn's lines through the app's structured
    handler and masks room, test and game codes out of the access log.
    """
    import uvicorn

    from vechnost_bot.monitoring import uvicorn_log_config

    uvicorn.run(
        "vechnost_bot.payments.web:app", host="0.0.0.0", port=port, log_level="info",
        log_config=uvicorn_log_config(),
    )


def serve_bot() -> None:
    """The bot process: long polling until SIGTERM."""
    print("[*] Starting Telegram bot...", flush=True)
    time.sleep(BOT_START_DELAY)
    from vechnost_bot import main

    main.main()


def _stop(processes: Sequence[Any], timeout: float) -> None:
    """SIGTERM every live process, then wait; kill whatever outlives `timeout`."""
    for process in processes:
        if process.is_alive():
            process.terminate()
    deadline = time.monotonic() + timeout
    for process in processes:
        process.join(max(0.0, deadline - time.monotonic()))
        if process.is_alive():
            print(f"[!] The {process.name} did not stop in time, killing it", flush=True)
            process.kill()
            process.join()


def supervise(
    children: Sequence[Child],
    stop_timeout: float = STOP_TIMEOUT,
    poll_interval: float = POLL_INTERVAL,
) -> int:
    """Start the children and watch them. Returns the exit code to leave with."""
    stop_requested: list[int] = []

    def request_stop(signum: int, _frame: object) -> None:
        stop_requested.append(signum)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    context = multiprocessing.get_context("spawn")
    processes = []
    for name, target, args in children:
        process = context.Process(target=target, args=args, name=name)
        process.start()
        processes.append(process)
    print(f"[*] Running: {', '.join(p.name for p in processes)}", flush=True)

    while True:
        if stop_requested:
            print(f"[*] Signal {stop_requested[0]} received, stopping services...", flush=True)
            _stop(processes, stop_timeout)
            print("[*] Services stopped", flush=True)
            return 0
        for process in processes:
            if not process.is_alive():
                print(
                    f"[!] The {process.name} died (exit code {process.exitcode}), "
                    "stopping the rest",
                    flush=True,
                )
                _stop([p for p in processes if p is not process], stop_timeout)
                return process.exitcode or 1
        time.sleep(poll_interval)


def main() -> int:
    port = int(os.getenv("PORT", "8000"))
    print(f"[*] Starting webhook server on port {port}...", flush=True)
    return supervise([
        ("webhook server", serve_web, (port,)),
        ("bot", serve_bot, ()),
    ])


if __name__ == "__main__":
    sys.exit(main())
