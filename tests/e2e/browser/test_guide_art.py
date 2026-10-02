"""The masterclass's pictures reach the reader, under the guide's own rules.

They are photographs the Library API serves (scripts/render_guide_art.py
renders them), and the page fetches each with the reader's initData as its
card nears the screen: an unpaid reader gets the free step's four and never
asks for another; a paying one opens the poses - held back behind a button
that asks the 18+ question, as the Library's categories are - and scrolls
into them.
"""

from __future__ import annotations

from ..harness import Server

POLL = 15_000
PICTURES = """() => [...document.querySelectorAll('#guide .art-photo')].map(slot => ({
    key: slot.dataset.art,
    ready: slot.classList.contains('ready'),
    width: slot.querySelector('img').naturalWidth,
}))"""
# What became of each picture: still a skeleton (never asked for, or still
# on its way), ready, or failed (the fetch or the image itself).
STATES = """() => [...document.querySelectorAll('#guide .art-photo')].map(
    slot => slot.dataset.art + ': ' + (slot.className.replace('art-photo', '').trim() || 'waiting')
)"""


def _until(phone, predicate: str, arg: str | None = None) -> None:
    """Wait for the pictures, and say what each one became if they never come."""
    try:
        phone.page.wait_for_function(predicate, arg=arg, timeout=POLL)
    except Exception as error:
        raise AssertionError(f"pictures not ready: {phone.page.evaluate(STATES)}") from error


def _open(phone, adult: bool = False) -> None:
    phone.screen("home")
    phone.page.click('[data-module="nude_guide"]')
    phone.screen("guide")
    phone.page.wait_for_selector("#guide .guide-item")
    if adult:
        phone.page.click("#guide .guide-nsfw")
        phone.page.wait_for_selector("#nsfw.show")
        phone.page.click("#nsfwYes")
        phone.page.wait_for_selector(
            '#guide .art-photo[data-art="her-1"]', state="attached", timeout=POLL
        )


def test_an_unpaid_reader_sees_the_light_step_in_pictures(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    asked: list[str] = []
    phone.page.on("request", lambda r: asked.append(r.url) if "/art/" in r.url else None)
    _open(phone)
    _until(phone, "() => document.querySelectorAll('#guide .art-photo.ready').length === 4")
    pictures = phone.page.evaluate(PICTURES)
    keys = [p["key"] for p in pictures]
    assert keys == ["light-side", "light-rim", "light-soft", "light-stripes"], keys
    assert all(p["ready"] and p["width"] == 540 for p in pictures), pictures
    assert asked and all("/art/light-" in url for url in asked), asked
    # Each asked for at its fingerprint: a picture re-rendered under the
    # same key is a new address, never the copy the browser kept.
    assert all("&v=" in url for url in asked), asked
    phone.shot("masterclass-unpaid")


def test_a_paying_reader_scrolls_into_the_poses(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    _open(phone, adult=True)
    slot = '#guide .art-photo[data-art="her-1"]'
    phone.page.locator(slot).scroll_into_view_if_needed()
    _until(phone, "(s) => document.querySelector(s).classList.contains('ready')", arg=slot)
    assert phone.page.locator(slot).evaluate("el => el.querySelector('img').naturalWidth") == 540
    phone.shot("masterclass-her-1")
