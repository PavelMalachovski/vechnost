"""«69 ступеней» speaks in suits, on both phones (audit D-39).

CLAUDE.md says it - no emoji on the board - and three were left anyway: a
map on the button that folds the map, fire over the finale and fireworks
over its end, plus a sparkle in front of «Ваш ход». The map button is a
drawing in the button's own colour now, the turn chip leads with the suit of
whoever moves, and the finale and its end show the two pieces that made it
to 69, in seat order as the map sets them.
"""

from __future__ import annotations

import re

from ..harness import Player, Server
from .app import S69_SUIT

POLL = 12_000
# Emoji and pictographs, the four card suits aside.
EMOJI = re.compile(
    "[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u265f\u2667-\u27bf\u2b00-\u2bff\ufe0f]"
)


def both_home(alice: Player, bob: Player, code: str) -> None:
    for _ in range(600):
        state = alice.ok("GET", f"/api/steps69/{code}")
        if state["both_home"]:
            return
        (alice if state["your_turn"] else bob).ok("POST", f"/api/steps69/{code}/roll")
    raise AssertionError("the pair never reached 69")


def test_the_board_and_its_finale_speak_in_suits(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "diamonds"})["code"]
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    state = alice.ok("GET", f"/api/steps69/{code}")
    theirs = S69_SUIT[state["partner"]["piece"]]

    phone = phones(alice, start_param=f"s69_{code}")
    phone.page.wait_for_selector("#nsfw.show")
    phone.page.click("#nsfwYes")
    phone.screen("s69Board")
    mover = "♦" if state["your_turn"] else theirs
    phone.page.wait_for_function(
        "(s) => document.getElementById('s69TurnChip').innerText.trim().startsWith(s + '\\u00a0')",
        arg=mover,
        timeout=POLL,
    )
    drawn = phone.page.evaluate("""() => {
        const button = document.getElementById('s69MapToggle');
        const svg = button.querySelector('svg');
        return {svg: !!svg, text: button.textContent.trim(),
                stroke: svg && getComputedStyle(svg).stroke, color: getComputedStyle(button).color};
    }""")
    assert drawn["svg"] and drawn["text"] == "", drawn
    assert drawn["stroke"] == drawn["color"], drawn
    assert not EMOJI.findall(phone.page.inner_text("#s69Board"))
    phone.shot("board")

    both_home(alice, bob, code)
    phone.page.wait_for_selector("#s69Finale.show", timeout=POLL)
    phone.shot("finale")
    assert phone.page.inner_text("#s69FinaleSuits").split() == ["♦", theirs]
    assert phone.page.get_attribute("#s69FinaleSuits span:first-child", "class") == "red"
    assert not EMOJI.findall(phone.page.inner_text("#s69Finale"))

    phone.tap("#s69FinaleChoices button")
    phone.page.wait_for_selector("#s69Done.show", timeout=POLL)
    phone.shot("done")
    assert phone.page.inner_text("#s69DoneSuits").split() == ["♦", theirs]
    assert not EMOJI.findall(phone.page.inner_text("#s69Done"))
