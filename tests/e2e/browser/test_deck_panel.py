"""The buttons under a deck and the counter over it (audit D-29, D-30), as
drawn on both phones.

- The forward button stands in the middle of every deck. The panel has
  three fixed slots - back, forward, share - and a deck that has no use for
  one (a room has no back, the Library no share) leaves it empty instead of
  closing up. It used to close up, and forward sat 36 px off the middle,
  to the left in a room and to the right in the Library.
- A deck of one card, the question of the day, has no panel, no hint and no
  bar: its two buttons could only ever be disabled.
- One counter, and it says what it counts: «Карта 1 из 30» on the card. A
  second one, «1 / 30», sat beside the bar, repeating the card's number
  without its unit. The bar is a gauge, and reads the card's words to a
  screen reader.
"""

from __future__ import annotations

import re

from ..harness import Server, code_from_invite
from .app import open_module, settle_card, wait_home

POLL = 12_000

# Every visible leaf on a screen that reads like a count - "3 / 20", "3 из
# 20" - except on the card peeking from under the top one.
COUNTS = """(screen) => [...document.querySelectorAll('#' + screen + ' *')]
    .filter(el => !el.children.length && el.offsetParent !== null && !el.closest('.card.under'))
    .map(el => el.innerText.replace(/\\u00a0/g, ' ').trim())
    .filter(t => /\\d+\\s*(\\/|из)\\s*\\d+/.test(t))"""


def forward_offset(phone, screen: str) -> float:
    """How far the forward button's centre is from the middle of its panel."""
    return float(
        phone.page.evaluate(
            """(screen) => {
                const panel = document.querySelector('#' + screen + ' .deck-controls');
                const p = panel.getBoundingClientRect();
                const m = panel.querySelector('.ctrl.main').getBoundingClientRect();
                return (m.left + m.width / 2) - (p.left + p.width / 2);
            }""",
            screen,
        )
    )


def plain(text: str | None) -> str:
    return (text or "").replace(" ", " ")


def open_first_deck(phone) -> None:
    phone.tap("#btnPlay")
    phone.screen("themes")
    phone.page.locator("#themeList .theme-card").first.tap()
    phone.screen("levels")
    phone.page.locator("#levelList .level-card").first.tap()


def test_forward_stands_in_the_middle_of_every_deck(server: Server, phones) -> None:
    solo = phones(server.player("Alice", paid=True))
    wait_home(solo)
    open_first_deck(solo)
    solo.screen("deck")
    settle_card(solo)
    assert solo.page.is_visible("#btnPrev") and solo.page.is_visible("#btnShare")
    assert abs(forward_offset(solo, "deck")) < 1

    host = phones(server.player("Carol", paid=True))
    wait_home(host)
    host.tap("#btnCoop")
    host.screen("coop")
    host.tap("#btnCoopCreate")
    host.screen("themes")
    host.page.locator("#themeList .theme-card").first.tap()
    host.screen("levels")
    host.page.locator("#levelList .level-card").first.tap()
    host.screen("invite")
    room = code_from_invite(host.text("#inviteCode"))
    server.player("Dave").ok("POST", f"/api/rooms/{room}/join")
    host.screen("deck", timeout=POLL)
    settle_card(host)
    host.shot("room")
    assert not host.page.is_visible("#btnPrev"), "a room turns forward only"
    assert abs(forward_offset(host, "deck")) < 1, "the room's forward slid into back's place"

    reader = phones(server.player("Erin", paid=True))
    wait_home(reader)
    open_module(reader, "practices_couples")
    reader.shot("library")
    assert abs(forward_offset(reader, "libDeck")) < 1, "the Library's forward slid right"


def test_the_question_of_the_day_is_a_card_and_nothing_to_press(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    wait_home(phone)
    open_module(phone, "reflection")
    phone.shot("daily")
    for part in (".deck-controls", ".hint", ".progress-wrap"):
        assert not phone.page.is_visible(f"#libDeck {part}"), f"{part} on a deck of one card"
    footer = plain(phone.text("#libStage .card.top .card-footer"))
    assert re.fullmatch(r"День \d+ из 365", footer), footer

    # A deck of more than one card has them all back.
    phone.press_back()
    phone.screen("library")
    phone.tap('#libraryList [data-module="practices_couples"]')
    phone.screen("libDeck")
    settle_card(phone, "#libStage")
    for part in (".deck-controls", ".hint", ".progress-wrap"):
        assert phone.page.is_visible(f"#libDeck {part}"), part


def test_one_counter_on_the_card_says_what_it_counts(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    wait_home(phone)
    open_first_deck(phone)
    phone.screen("deck")
    settle_card(phone)
    footer = plain(phone.text("#stage .card.top .card-footer"))
    total = int(re.fullmatch(r"Карта 1 из (\d+)", footer).group(1))  # type: ignore[union-attr]
    assert phone.page.evaluate(COUNTS, "deck") == [footer], "a second counter on the screen"

    bar = "#progressTrack"
    assert phone.page.get_attribute(bar, "role") == "progressbar"
    assert phone.page.get_attribute(bar, "aria-label") == "Колода"
    assert phone.page.get_attribute(bar, "aria-valuenow") == "1"
    assert phone.page.get_attribute(bar, "aria-valuemax") == str(total)
    assert plain(phone.page.get_attribute(bar, "aria-valuetext")) == footer

    phone.tap("#btnNext")
    phone.page.wait_for_function(
        "() => document.getElementById('progressTrack').getAttribute('aria-valuenow') === '2'"
    )
    settle_card(phone)
    assert plain(phone.text("#stage .card.top .card-footer")) == f"Карта 2 из {total}"

    # The Library's cards count the same way.
    phone.press_back()
    phone.screen("levels")
    phone.press_back()
    phone.screen("themes")
    phone.press_back()
    wait_home(phone)
    open_module(phone, "practices_couples")
    footer = plain(phone.text("#libStage .card.top .card-footer"))
    assert re.fullmatch(r"Карта 1 из \d+", footer), footer
    assert phone.page.evaluate(COUNTS, "libDeck") == [footer]
