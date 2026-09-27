"""Phones: which models, which engines, and one person's phone with the app open.

Telegram shows a Mini App in Chromium on Android and in WebKit on iOS, so a
phone here is a screen, a pixel ratio, a touch screen and a user agent,
drawn by the engine that phone really uses:

* **android** – a Pixel-class phone, 412×915 at 2.625x, in Chromium;
* **iphone** – an iPhone 15 Pro-class phone, 393×852 at 3x, in WebKit.

Both partners of a two-phone scenario hold the same kind of phone, so one CI
job per phone runs every scenario on one engine (`E2E_PHONES` picks which).
`conftest.py` turns this into fixtures; this module is the machinery,
importable by anything that needs a phone of its own (the screen tour, the
fuzzer).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from ..harness import Player
from .touch import Finger, finger_for

STUB = (Path(__file__).parent / "telegram_stub.js").read_text(encoding="utf-8")
TELEGRAM_JS = "https://telegram.org/js/telegram-web-app.js"
REPORT_DIR = Path(os.environ.get("E2E_REPORT_DIR", "e2e-report")) / "browser"
# Serve this file as the Mini App page instead of the server's own. It is how
# a test is shown to catch a bug: put the bug back in a scratch copy of
# webapp/index.html and watch the test fail. Fonts, art and the API still
# come from the server.
WEBAPP_HTML = os.environ.get("E2E_WEBAPP_HTML", "")
# Console lines that are the app working as designed: the engine's note on
# every non-2xx fetch (Chromium and WebKit word it alike), and the app's own
# `console.error('API', status, ...)` for a 4xx it then explains to the user
# - a 404 from /api/steps69/mine is "no game in play", a 409 on join is "the
# seat is taken". Real failures are caught from the responses themselves:
# any 5xx fails the test.
BENIGN_CONSOLE = re.compile(r"^(Failed to load resource|API 4\d\d )")


def bot_token() -> str:
    """The token the server under test signs initData with."""
    return os.environ.get("E2E_BOT_TOKEN") or os.environ["TELEGRAM_BOT_TOKEN"]


@dataclass(frozen=True)
class Device:
    """A phone model: its screen, and the engine that draws it."""

    name: str        # "android" / "iphone": test ids, file names and logs say this
    title: str       # what a person would call it
    engine: str      # "chromium" / "webkit"
    platform: str    # what Telegram.WebApp.platform reports on it
    width: int
    height: int
    scale: float     # device pixels per CSS pixel
    ua_from: str     # the Playwright descriptor whose user agent it borrows

    @property
    def label(self) -> str:
        return f"{self.title} ({self.width}x{self.height}, {self.engine})"

    def context_options(self, playwright: Any) -> dict[str, Any]:
        size = {"width": self.width, "height": self.height}
        return {
            "viewport": size,
            "screen": size,
            "device_scale_factor": self.scale,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": playwright.devices[self.ua_from]["user_agent"],
            "locale": "ru-RU",
        }


ANDROID = Device("android", "Android, Pixel-class", "chromium", "android",
                 412, 915, 2.625, "Pixel 7")
IPHONE = Device("iphone", "iPhone 15 Pro-class", "webkit", "ios",
                393, 852, 3, "iPhone 15 Pro")
DEVICES = {device.name: device for device in (ANDROID, IPHONE)}


def chosen_phones() -> tuple[list[Device], bool]:
    """The phones this run plays on, and whether they were asked for by name.

    `E2E_PHONES=android` (or `iphone`, or both, comma-separated) is how a CI
    job runs one phone; unset, both run and a phone whose engine is missing
    here skips. Asked for by name, a missing engine is a failure instead: a
    job that was meant to test the iPhone must not pass by testing nothing.
    """
    given = os.environ.get("E2E_PHONES", "").strip()
    if not given:
        return list(DEVICES.values()), False
    names = [name.strip() for name in given.split(",") if name.strip()]
    unknown = sorted(set(names) - set(DEVICES))
    if unknown:
        raise pytest.UsageError(f"E2E_PHONES names no such phone: {unknown}; known: {sorted(DEVICES)}")
    return [DEVICES[name] for name in names], True


PHONES, PHONES_NAMED = chosen_phones()


class Engines:
    """The browser engines, each launched the first time a test asks for it.

    An engine that is not installed is remembered, and every test that needs
    it skips with the same reason instead of failing - WebKit in particular
    is installed in CI and usually nowhere else - unless the run asked for
    that phone by name (`required`), when it fails.
    """

    def __init__(self, playwright: Any, required: bool = False) -> None:
        self.playwright = playwright
        self.required = required
        self._launched: dict[str, Any] = {}
        self._missing: dict[str, str] = {}

    def get(self, name: str) -> Any:
        if name not in self._launched and name not in self._missing:
            try:
                self._launched[name] = getattr(self.playwright, name).launch()
            except Exception as e:  # not installed on this machine
                first = (str(e).strip().splitlines() or [repr(e)])[0]
                self._missing[name] = (
                    f"{name} is not installed here ({first}); CI installs it with "
                    f"`python -m playwright install --with-deps {name}`"
                )
        if name in self._missing:
            if self.required:
                pytest.fail(self._missing[name] + ", and E2E_PHONES asked for it by name")
            pytest.skip(self._missing[name])
        return self._launched[name]

    def close(self) -> None:
        for browser in self._launched.values():
            browser.close()


@dataclass
class ApiCall:
    """One /api request a phone made, and how it ended."""

    method: str
    path: str       # path and query, as the app asked
    status: int     # 0: no response at all (aborted, refused, timed out)
    note: str = ""  # why it failed, when it did not get a response

    def __str__(self) -> str:
        return f"{self.method} {self.path} -> {self.status or self.note}"


@dataclass
class Phone:
    """One person's phone with the Mini App open."""

    name: str
    player: Player
    page: Any
    context: Any
    shots: Path
    device: Device = ANDROID
    base_url: str = ""
    start_param: str | None = None
    # Merged into Telegram.WebApp by the stub: platform, version, ...
    telegram: dict[str, Any] = field(default_factory=dict)
    # Served as the Mini App page in place of the server's own (see WEBAPP_HTML).
    webapp_html: str | None = None
    errors: list[str] = field(default_factory=list)
    api: list[ApiCall] = field(default_factory=list)
    step: int = 0
    _finger: Finger | None = None

    def screen(self, screen_id: str, timeout: float = 15_000) -> None:
        """Wait until the app shows this screen."""
        self.page.wait_for_selector(f"section#{screen_id}.active", timeout=timeout)

    def shot(self, label: str) -> None:
        self.step += 1
        self.shots.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(self.shots / f"{self.step:02d}-{self.name}-{label}.png"))

    def text(self, selector: str) -> str:
        return str(self.page.locator(selector).first.inner_text()).strip()

    def tap(self, selector: str, timeout: float = 15_000) -> None:
        """A finger tap on an element, after Playwright's actionability checks.

        Playwright's own tap: CDP touch in Chromium, WebKit's touchscreen in
        WebKit - the same input path `finger.tap` takes, aimed by selector.
        """
        self.page.locator(selector).first.tap(timeout=timeout)

    @property
    def finger(self) -> Finger:
        """A finger on this phone's glass: touch.py says what each engine allows."""
        if self._finger is None:
            self._finger = finger_for(self.page, self.context, self.device.engine)
        return self._finger

    # -- Telegram around the app -------------------------------------------

    def stub(self) -> str:
        unsafe: dict[str, Any] = {
            "user": self.player.user, "auth_date": int(time.time()), "hash": "e2e",
        }
        if self.start_param:
            unsafe["start_param"] = self.start_param
        init = {
            "initData": self.player.init_data,
            "initDataUnsafe": unsafe,
            "platform": self.device.platform,
            **self.telegram,
        }
        return STUB.replace("__INIT__", json.dumps(init, ensure_ascii=False))

    def open_link(self, start_param: str | None) -> None:
        """Telegram opens the app again, from a link carrying this payload."""
        self.start_param = start_param
        self.page.goto(f"{self.base_url}/app/")

    def back_button_visible(self) -> bool:
        return bool(self.page.evaluate(
            "() => !!(window.Telegram && Telegram.WebApp.BackButton"
            " && Telegram.WebApp.BackButton.isVisible)"
        ))

    def press_back(self) -> None:
        """Telegram's own Back button: the header arrow, Android's back gesture."""
        self.page.evaluate(
            "() => { const b = Telegram.WebApp.BackButton; if (b && b._cb) b._cb(); }"
        )

    def route(self, route: Any, request: Any) -> None:
        # One handler for every request, because Playwright tries routes
        # newest-first: a separate catch-all registered after the stub's
        # route aborted Telegram's script before the stub could answer it.
        # Nothing but the app and the stub: a test must not depend on the
        # network, and must not call anyone.
        url = request.url
        if url.startswith(TELEGRAM_JS):
            route.fulfill(body=self.stub(), content_type="application/javascript")
        elif url.startswith(self.base_url):
            if urlsplit(url).path in ("/app", "/app/", "/app/index.html"):
                if self.webapp_html is not None:
                    route.fulfill(body=self.webapp_html, content_type="text/html; charset=utf-8")
                    return
                if WEBAPP_HTML:
                    route.fulfill(path=WEBAPP_HTML, content_type="text/html; charset=utf-8")
                    return
            # Each phone on its own network, as far as the proxy can tell.
            route.continue_(headers={**request.headers, "x-forwarded-for": self.player.ip})
        else:
            route.abort()

    def _watch(self) -> None:
        """Record what the app does wrong, and every /api call it makes."""

        def on_console(message: Any) -> None:
            if message.type == "error" and not BENIGN_CONSOLE.match(message.text):
                self.errors.append(f"console: {message.text}")

        def api_path(url: str) -> str | None:
            if not url.startswith(self.base_url):
                return None
            parts = urlsplit(url)
            if not parts.path.startswith("/api/"):
                return None
            return parts.path + (f"?{parts.query}" if parts.query else "")

        # Requests that got an answer. Chromium reports a request that was
        # answered with no body (the 204 of /api/events) as failed with
        # net::ERR_ABORTED right after its response: that is not a failure.
        answered: set[int] = set()

        def on_response(response: Any) -> None:
            if response.status >= 500:
                self.errors.append(f"{response.status} from {response.url}")
            path = api_path(response.url)
            if path is not None:
                answered.add(id(response.request))
                self.api.append(ApiCall(response.request.method, path, response.status))

        def on_failed(request: Any) -> None:
            path = api_path(request.url)
            if path is not None and id(request) not in answered:
                failure = request.failure
                note = failure if isinstance(failure, str) else str(failure or "failed")
                self.api.append(ApiCall(request.method, path, 0, note))

        self.page.on("console", on_console)
        self.page.on("pageerror", lambda error: self.errors.append(f"pageerror: {error}"))
        self.page.on("response", on_response)
        self.page.on("requestfailed", on_failed)


def open_phone(
    engines: Engines,
    base_url: str,
    player: Player,
    *,
    shots: Path,
    device: Device = ANDROID,
    start_param: str | None = None,
    viewport: dict[str, int] | None = None,
    telegram: dict[str, Any] | None = None,
    init_script: str | None = None,
    webapp_html: str | None = None,
    trace: bool = True,
    goto: bool = True,
    reduced_motion: bool = False,
) -> Phone:
    """A phone of this model with the Mini App open, signed in as `player`.

    `webapp_html` serves that text as the page instead of the server's own:
    how a test shows it would catch a fault, by putting the fault back.
    `reduced_motion` is the phone's own setting, so the app reads it at
    launch the way it would on a phone that asks for less motion.
    """
    browser = engines.get(device.engine)
    options = device.context_options(engines.playwright)
    if viewport:
        options["viewport"] = viewport
    if reduced_motion:
        options["reduced_motion"] = "reduce"
    context = browser.new_context(**options)
    if trace:
        context.tracing.start(screenshots=True, snapshots=True)
    page = context.new_page()
    phone = Phone(
        player.name, player, page, context, shots, device=device,
        base_url=base_url, start_param=start_param, telegram=dict(telegram or {}),
        webapp_html=webapp_html,
    )
    context.route("**/*", phone.route)
    if init_script:
        # Runs before the app's own script, in every page of the phone.
        context.add_init_script(init_script)
    phone._watch()
    if goto:
        page.goto(f"{base_url}/app/")
    return phone


def close_phones(opened: list[Phone], shots: Path, *, failed: bool) -> list[str]:
    """Close every phone; the errors they collected, one line each."""
    for phone in opened:
        try:
            phone.shot("final")
        except Exception:
            pass
        trace = shots / f"trace-{phone.name}.zip" if failed else None
        if trace is not None:
            shots.mkdir(parents=True, exist_ok=True)
        try:
            phone.context.tracing.stop(path=str(trace) if trace else None)
        except Exception:
            pass  # tracing was never started on this phone
        phone.context.close()
    return [f"{phone.name}: {error}" for phone in opened for error in phone.errors]
