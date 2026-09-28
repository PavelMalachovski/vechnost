"""Telegram's own chrome and the page meet without a seam (audit D-24).

- Telegram paints its header, the background behind the page and, from Bot
  API 7.10, the bottom bar in the app's darkest aubergine. A client before
  6.9 takes only a theme key for the header and threw on the colour, which
  also skipped the background after it: it gets the key now, and the
  background anyway.
- The glow rises out of that same colour. It began at its brightest right
  under the header, and the two met in a line across the top of every
  screen.
- The page stays clear of the notch and of Telegram's own controls: in full
  screen the controls sit inside the device's safe area, so the two insets
  add up. The page used to take the larger of them.
"""

from __future__ import annotations

import io

from PIL import Image

from ..harness import Server
from .app import wait_home

SHELL = (0x1C, 0x04, 0x14)


def calls(phone, name: str) -> list[str]:
    return [call[1] for call in phone.page.evaluate("() => window.__tg.calls") if call[0] == name]


def row(phone, y: int) -> list[tuple[int, int, int]]:
    """The page's pixels along one row, left to right, one per CSS pixel.

    The last pixel is left out: a phone's width times its pixel ratio is
    rarely whole (412 x 2.625 on the Android phone), and the clip's edge
    cuts a device pixel in two."""
    width = phone.page.viewport_size["width"] - 1
    png = phone.page.screenshot(clip={"x": 0, "y": y, "width": width, "height": 1}, scale="css")
    image = Image.open(io.BytesIO(png)).convert("RGB")
    return [image.getpixel((x, 0)) for x in range(image.width)]


def near(pixel: tuple[int, int, int], colour: tuple[int, int, int], by: int = 3) -> bool:
    return all(abs(a - b) <= by for a, b in zip(pixel, colour, strict=True))


def test_telegram_s_chrome_is_the_app_s_colour(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    wait_home(phone)
    assert calls(phone, "setHeaderColor") == ["#1C0414"]
    assert calls(phone, "setBackgroundColor") == ["#1C0414"]
    assert calls(phone, "setBottomBarColor") == ["#1C0414"]


def test_a_client_before_6_9_gets_a_header_it_accepts(server: Server, phones) -> None:
    phone = phones(server.player("Alice"), telegram={"version": "6.7"})
    wait_home(phone)
    assert calls(phone, "setHeaderColor") == ["bg_color"]
    assert calls(phone, "setBackgroundColor") == ["#1C0414"], "the background went with the header"
    assert calls(phone, "setBottomBarColor") == [], "a bottom bar colour before 7.10"


def test_the_top_of_every_screen_is_the_header_s_colour(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    wait_home(phone)
    top = row(phone, 0)
    off = [x for x, pixel in enumerate(top) if not near(pixel, SHELL)]
    assert not off, f"the top edge leaves the header's colour at x={off[:5]}: {top[off[0]]}"
    # ...and the glow is still there below it.
    middle = row(phone, 60)[len(top) // 2]
    assert sum(middle) > sum(SHELL) + 30, f"no glow under the header: {middle}"
    phone.shot("top")


def test_the_page_clears_the_notch_and_telegram_s_controls(server: Server, phones) -> None:
    phone = phones(
        server.player("Alice"),
        telegram={
            "safeAreaInset": {"top": 30, "bottom": 20, "left": 0, "right": 0},
            "contentSafeAreaInset": {"top": 40, "bottom": 6, "left": 0, "right": 0},
        },
    )
    wait_home(phone)
    padding = phone.page.evaluate("""() => {
        const s = getComputedStyle(document.getElementById('home'));
        return [parseFloat(s.paddingTop), parseFloat(s.paddingBottom)];
    }""")
    # 14px and 18px are the screen's own margins inside the safe area.
    assert padding == [30 + 40 + 14, 20 + 6 + 18], padding
    phone.shot("full-screen")
