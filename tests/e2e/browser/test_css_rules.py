"""What the stylesheet means, as the phone draws it (audit D-26, D-27, D-28).

- A paragraph's own class wins over the box's default for paragraphs: the
  18+ line on the board's door is its own small pink, not the box's grey.
- A full-width button's glow reaches the edge of the phone: the list it
  sits in clips at the phone's edges, not 18px inside them.
- A list starts at the top, under its title, in the same place on every
  list screen; the home screen and a door stay in the middle.
"""

from __future__ import annotations

from ..harness import Server
from .app import wait_home

# From the top of its screen, which slides 12px as it comes in: the two
# rectangles move together, so the difference holds mid-slide.
TOP_OF = """(sel) => {
    const el = document.querySelector(sel);
    return el.getBoundingClientRect().top - el.closest('.screen').getBoundingClientRect().top;
}"""


def first_row_top(phone, selector: str) -> float:
    phone.page.wait_for_selector(selector)
    return float(phone.page.evaluate(TOP_OF, selector))


def press_back(phone) -> None:
    phone.page.evaluate("() => window.Telegram.WebApp.BackButton._cb()")


def test_a_paragraph_keeps_its_own_class(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    wait_home(phone)
    phone.tap("#btnS69")
    phone.page.wait_for_selector("#nsfw.show")
    phone.tap("#nsfwYes")
    phone.screen("s69")
    got = phone.page.evaluate("""() => {
        const cs = (sel) => getComputedStyle(document.querySelector(sel));
        const box = cs('#s69 .coop-box > p:not([class])');
        return {age: cs('.s69-age').fontSize, ageColor: cs('.s69-age').color,
                intro: cs('.s69-intro').lineHeight, introSize: cs('.s69-intro').fontSize,
                box: box.fontSize, boxColor: box.color};
    }""")
    assert got["age"] == "12.5px", got
    assert got["ageColor"] != got["boxColor"], "the 18+ line is the box's grey"
    assert got["intro"] == f"{14 * 1.55:g}px", got


def test_a_buttons_glow_reaches_the_edge_of_the_phone(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    wait_home(phone)
    phone.tap("#btnCoop")
    phone.screen("coop")
    box = phone.page.evaluate("""() => {
        const r = document.querySelector('#coop .coop-box').getBoundingClientRect();
        const b = document.getElementById('btnCoopCreate').getBoundingClientRect();
        return {left: r.left, right: r.right, width: document.documentElement.clientWidth,
                button: b.left, buttonRight: b.right};
    }""")
    assert box["left"] <= 0 and box["right"] >= box["width"], f"the clip is inside the phone: {box}"
    assert box["button"] == 18 and box["buttonRight"] == box["width"] - 18, (
        f"the button left the screen's margin: {box}"
    )


def test_every_list_starts_in_the_same_place(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    wait_home(phone)
    phone.tap("#btnPlay")
    phone.screen("themes")
    themes = first_row_top(phone, "#themeList .theme-card")
    phone.page.locator("#themeList .theme-card").first.tap()
    phone.screen("levels")
    levels = first_row_top(phone, "#levelList .level-card")
    press_back(phone)
    phone.screen("themes")
    press_back(phone)
    wait_home(phone)
    phone.tap("#btnPractices")
    phone.screen("library")
    library = first_row_top(phone, "#libraryList [data-module]")
    phone.tap('#libraryList [data-module="dates"]')
    phone.screen("libraryDetail")
    categories = first_row_top(phone, "#libDetailBody .lib-cat")
    tops = {"themes": themes, "levels": levels, "library": library, "categories": categories}
    assert max(tops.values()) - min(tops.values()) <= 1, f"lists start in different places: {tops}"
