"""The masterclass's pictures reach the reader, under the guide's own rules.

They are photographs the Library API serves (scripts/render_guide_art.py
renders them), and the page fetches each with the reader's initData as its
card nears the screen: an unpaid reader gets the free step's four and never
asks for another, a paying one past the 18+ question scrolls into the poses.
"""

from __future__ import annotations

from ..harness import Server

POLL = 15_000
PICTURES = """() => [...document.querySelectorAll('#guide .art-photo')].map(slot => ({
    key: slot.dataset.art,
    ready: slot.classList.contains('ready'),
    width: slot.querySelector('img').naturalWidth,
}))"""


def _open(phone) -> None:
    phone.screen("home")
    phone.page.click('[data-module="nude_guide"]')
    phone.page.wait_for_selector("#nsfw.show, #guide.active")
    if phone.page.is_visible("#nsfwYes"):
        phone.page.click("#nsfwYes")
    phone.screen("guide")
    phone.page.wait_for_selector("#guide .guide-item")


def test_an_unpaid_reader_sees_the_light_step_in_pictures(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    asked: list[str] = []
    phone.page.on("request", lambda r: asked.append(r.url) if "/art/" in r.url else None)
    _open(phone)
    phone.page.wait_for_function(
        "() => document.querySelectorAll('#guide .art-photo.ready').length === 4", timeout=POLL
    )
    pictures = phone.page.evaluate(PICTURES)
    keys = [p["key"] for p in pictures]
    assert keys == ["light-side", "light-rim", "light-soft", "light-stripes"], keys
    assert all(p["ready"] and p["width"] == 540 for p in pictures), pictures
    assert asked and all("/art/light-" in url for url in asked), asked
    phone.shot("masterclass-unpaid")


def test_a_paying_reader_scrolls_into_the_poses(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    _open(phone)
    slot = '#guide .art-photo[data-art="her-1"]'
    phone.page.locator(slot).scroll_into_view_if_needed()
    phone.page.wait_for_function(
        "(s) => document.querySelector(s).classList.contains('ready')", arg=slot, timeout=POLL
    )
    assert phone.page.locator(slot).evaluate("el => el.querySelector('img').naturalWidth") == 540
    phone.shot("masterclass-her-1")
