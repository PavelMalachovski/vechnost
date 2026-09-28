"""Two phones: two browser contexts, each a different Telegram user.

Each context is its own phone - its own storage, its own cookies - and gets
its own copy of Telegram's WebApp object carrying that user's initData,
signed with the bot token the server checks. So the server sees two real
users, and the Mini App cannot tell it is not inside Telegram. Each phone
also sends its own `X-Forwarded-For`, as two phones on two networks do.

Every test that opens phones runs once per phone model (`phones.py`): an
Android phone in Chromium and an iPhone in WebKit, the two engines Telegram
shows a Mini App in. Both partners of a scenario hold the same model, so a
CI job per phone runs every scenario on one engine; `E2E_PHONES` picks the
phones (`android`, `iphone`, or both, the default). Where an engine is not
installed its tests skip and say why - unless `E2E_PHONES` named that phone,
when they fail: a job meant to test the iPhone must not pass by testing
nothing.

The server is a real uvicorn: the one at E2E_BASE_URL (CI starts it on
PostgreSQL), or one this module starts on a throwaway SQLite file.

Opt-in: these run with E2E_BROWSER=1, because they need browsers and take
minutes. Screenshots of every step go to E2E_REPORT_DIR/browser/, and a
Playwright trace of each phone is kept when a test fails.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from ..harness import (
    E2E_BOT_USERNAME,
    E2E_TRIBUTE_KEY,
    Player,
    Server,
    ServerError,
)
from . import design
from .phones import (
    DEVICES,
    PHONES,
    PHONES_NAMED,
    REPORT_DIR,
    Device,
    Engines,
    Phone,
    bot_token,
    close_phones,
    open_phone,
)
from .screens import Atlas, Tour, save_atlas

pytestmark = pytest.mark.browser


def pytest_configure(config: pytest.Config) -> None:
    # Registered here rather than in pyproject.toml: they only mean something
    # to this directory, and CI selects by them (.github/workflows/e2e.yml).
    config.addinivalue_line(
        "markers", "screens: The screen tour: every screen, four sizes, each phone (browser)"
    )
    config.addinivalue_line(
        "markers", "ui_fuzz: Two phones tapping at random (budget: E2E_UI_FUZZ_RUNS/_STEPS)"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("E2E_BROWSER") == "1":
        return
    skip = pytest.mark.skip(reason="browser E2E is opt-in: set E2E_BROWSER=1")
    for item in items:
        if "tests/e2e/browser/" in item.nodeid.replace("\\", "/"):
            item.add_marker(skip)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def live_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real server over real HTTP, with payments on."""
    given = os.environ.get("E2E_BASE_URL", "").rstrip("/")
    if given:
        yield given
        return
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    db = tmp_path_factory.mktemp("browser") / "e2e.db"
    env = {
        **os.environ,
        "ENABLE_PAYMENT": "true",
        "TRIBUTE_API_KEY": E2E_TRIBUTE_KEY,
        "DATABASE_URL": os.environ.get("E2E_DATABASE_URL") or f"sqlite+aiosqlite:///{db}",
        "BOT_USERNAME": E2E_BOT_USERNAME,
        "WEBAPP_URL": f"{url}/app/",
        "TRUSTED_PROXY_HOPS": "1",
        "LOG_LEVEL": "WARNING",
    }
    env.pop("SENTRY_DSN", None)
    log = open(tmp_path_factory.mktemp("browser-log") / "uvicorn.log", "w")  # noqa: SIM115
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "vechnost_bot.payments.web:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise RuntimeError(f"uvicorn did not come up; see {log.name}")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


@pytest.fixture
def server(live_url: str) -> Iterator[Server]:
    """The API side of the same server, for buying access the way Tribute sells it."""
    with httpx.Client(base_url=live_url, timeout=30) as http:
        yield Server(http, live=True, bot_token=bot_token())


@pytest.fixture(scope="session")
def engines() -> Iterator[Engines]:
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        found = Engines(playwright, required=PHONES_NAMED)
        yield found
        found.close()


@pytest.fixture(params=[device.name for device in PHONES])
def device(request: pytest.FixtureRequest, engines: Engines) -> Device:
    """The phone model this run of the test is on: `android` or `iphone`."""
    chosen = DEVICES[request.param]
    engines.get(chosen.engine)  # skip, or fail, before the first phone opens
    return chosen


@pytest.fixture(scope="session", params=[device.name for device in PHONES])
def atlas(request: pytest.FixtureRequest, engines: Engines, live_url: str) -> Iterator[Atlas]:
    """One tour of every screen per phone model (screens.py), with the design
    lint looking at each stop, shared by whatever inspects it."""
    device = DEVICES[request.param]
    engines.get(device.engine)
    with httpx.Client(base_url=live_url, timeout=30) as http:
        tour = Tour(
            engines,
            live_url,
            Server(http, live=True, bot_token=bot_token()),
            device,
            visitors=[design.visitor],
        )
        found = tour.run()
    save_atlas(found)
    yield found


@pytest.fixture
def browser(engines: Engines, device: Device) -> Any:
    """The engine that draws this phone, for a test that builds its own page."""
    return engines.get(device.engine)


@pytest.fixture
def phones(
    engines: Engines, live_url: str, device: Device, request: pytest.FixtureRequest
) -> Iterator[Callable[..., Phone]]:
    """`phones(player, start_param=None, init_script=None, ...)` -> a Phone
    of this run's model with the app loaded (see `phones.open_phone`)."""
    opened: list[Phone] = []
    shots = REPORT_DIR / request.node.name

    def open_one(player: Player, start_param: str | None = None, **options: Any) -> Phone:
        options.setdefault("device", device)
        phone = open_phone(
            engines, live_url, player, shots=shots, start_param=start_param, **options
        )
        # The same person on a second phone gets a name of their own, or the
        # two would write over each other's screenshots and trace.
        taken = sum(1 for other in opened if other.player is player)
        if taken:
            phone.name = f"{phone.name}{taken + 1}"
        opened.append(phone)
        return phone

    yield open_one

    failed = getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed
    problems = close_phones(opened, shots, failed=failed)
    if problems:
        raise ServerError("the app misbehaved in the browser:\n" + "\n".join(problems))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.rep_call = report  # type: ignore[attr-defined]
