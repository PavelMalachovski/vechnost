"""Two phones: two Chromium contexts, each a different Telegram user.

Each context is its own phone — its own storage, its own cookies — and gets
its own copy of Telegram's WebApp object carrying that user's initData,
signed with the bot token the server checks. So the server sees two real
users, and the Mini App cannot tell it is not inside Telegram.

The server is a real uvicorn: the one at E2E_BASE_URL (CI starts it on
PostgreSQL), or one this module starts on a throwaway SQLite file.

Opt-in: these run with E2E_BROWSER=1, because they need Chromium and take
a minute. Screenshots of every step go to E2E_REPORT_DIR/browser/, and a
Playwright trace of each phone is kept when a test fails.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
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

pytestmark = pytest.mark.browser

STUB = (Path(__file__).parent / "telegram_stub.js").read_text(encoding="utf-8")
REPORT_DIR = Path(os.environ.get("E2E_REPORT_DIR", "e2e-report")) / "browser"
# Console lines that are the app working as designed: Chromium's note on
# every non-2xx fetch, and the app's own `console.error('API', status, ...)`
# for a 4xx it then explains to the user — a 404 from /api/steps69/mine is
# "no game in play", a 409 on join is "the seat is taken". Real failures are
# caught from the responses themselves: any 5xx fails the test.
BENIGN_CONSOLE = re.compile(r"^(Failed to load resource|API 4\d\d )")


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
        [sys.executable, "-m", "uvicorn", "vechnost_bot.payments.web:app",
         "--host", "127.0.0.1", "--port", str(port)],
        env=env, stdout=log, stderr=subprocess.STDOUT,
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
    token = os.environ.get("E2E_BOT_TOKEN") or os.environ["TELEGRAM_BOT_TOKEN"]
    with httpx.Client(base_url=live_url, timeout=30) as http:
        yield Server(http, live=True, bot_token=token)


@pytest.fixture(scope="session")
def chromium() -> Iterator[Any]:
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as e:  # no browser installed on this machine
            pytest.skip(f"Chromium is not available: {e}")
        yield browser
        browser.close()


@dataclass
class Phone:
    """One person's phone with the Mini App open."""

    name: str
    player: Player
    page: Any
    context: Any
    shots: Path
    errors: list[str] = field(default_factory=list)
    step: int = 0

    def screen(self, screen_id: str, timeout: float = 15_000) -> None:
        """Wait until the app shows this screen."""
        self.page.wait_for_selector(f"section#{screen_id}.active", timeout=timeout)

    def shot(self, label: str) -> None:
        self.step += 1
        self.shots.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(self.shots / f"{self.step:02d}-{self.name}-{label}.png"))

    def text(self, selector: str) -> str:
        return str(self.page.locator(selector).first.inner_text()).strip()


@pytest.fixture
def phones(chromium: Any, live_url: str, request: pytest.FixtureRequest) -> Iterator[Any]:
    """`open_phone(player, start_param=None)` -> a Phone with the app loaded."""
    opened: list[Phone] = []
    shots = REPORT_DIR / request.node.name

    def open_phone(player: Player, start_param: str | None = None) -> Phone:
        context = chromium.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            locale="ru-RU",
        )
        context.tracing.start(screenshots=True, snapshots=True)
        unsafe = {"user": player.user, "auth_date": int(time.time()), "hash": "e2e"}
        if start_param:
            unsafe["start_param"] = start_param
        stub = STUB.replace("__INIT__", json.dumps({
            "initData": player.init_data, "initDataUnsafe": unsafe,
        }))
        # One handler for every request, because Playwright tries routes
        # newest-first: a separate catch-all registered after the stub's
        # route aborted Telegram's script before the stub could answer it.
        # Nothing but the app and the stub: a test must not depend on the
        # network, and must not call anyone.
        def route_request(route: Any, request: Any, body: str = stub) -> None:
            url = request.url
            if url.startswith("https://telegram.org/js/telegram-web-app.js"):
                route.fulfill(body=body, content_type="application/javascript")
            elif url.startswith(live_url):
                route.continue_()
            else:
                route.abort()

        context.route("**/*", route_request)
        page = context.new_page()
        phone = Phone(player.name, player, page, context, shots)

        def on_console(message: Any) -> None:
            if message.type == "error" and not BENIGN_CONSOLE.match(message.text):
                phone.errors.append(f"console: {message.text}")

        def on_response(response: Any) -> None:
            if response.status >= 500:
                phone.errors.append(f"{response.status} from {response.url}")

        page.on("console", on_console)
        page.on("pageerror", lambda error: phone.errors.append(f"pageerror: {error}"))
        page.on("response", on_response)
        page.goto(f"{live_url}/app/")
        opened.append(phone)
        return phone

    yield open_phone

    failed = getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed
    for phone in opened:
        try:
            phone.shot("final")
        except Exception:
            pass
        trace = shots / f"trace-{phone.name}.zip" if failed else None
        if trace is not None:
            shots.mkdir(parents=True, exist_ok=True)
        phone.context.tracing.stop(path=str(trace) if trace else None)
        phone.context.close()
    problems = [f"{phone.name}: {error}" for phone in opened for error in phone.errors]
    if problems:
        raise ServerError("the app misbehaved in the browser:\n" + "\n".join(problems))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.rep_call = report  # type: ignore[attr-defined]
