"""«69 ступеней»: the board as it is drawn, on both phones.

The board climbs from the bottom nine squares a row, like the Lila board it
is drawn after, and is shown whole - never a scroller, never pushing the
dice off the phone. A ladder is a Cupid's arrow from its square to the one
it carries the piece to, a snake a serpent with its head on its square and
its tail on the one it drops the piece to, and a piece that lands on either
rides it. A square is a picture: a tap on it opens nothing, because what a
square asks reaches a player only once their piece stands on it (the board
payload carries no task at all: test_steps69_api.py).
"""

from __future__ import annotations

from typing import Any

from ..harness import Player, Server
from .app import resize

POLL = 12_000

# Where the board stands in the phone: every square inside the map, the map
# inside the screen and not a scroller, and the dice under it within reach.
BOARD_IN_VIEW = """() => {
  const map = document.getElementById('s69Map');
  const m = map.getBoundingClientRect();
  const inside = (r, o) => r.left >= o.left - 1 && r.right <= o.right + 1
                        && r.top >= o.top - 1 && r.bottom <= o.bottom + 1;
  const screen = {left: 0, top: 0, right: innerWidth, bottom: innerHeight};
  const cells = [...map.querySelectorAll('.s69-cell')];
  const dice = document.getElementById('s69Dice');
  return {
    cells: cells.length,
    outside: cells.filter(c => !inside(c.getBoundingClientRect(), m)).map(c => c.dataset.id),
    map: inside(m, screen),
    scrolls: map.scrollHeight > map.clientHeight + 1,
    dice: dice.style.display === 'none' || inside(dice.getBoundingClientRect(), screen),
    piece: !!map.querySelector('.s69-cell.here .s69-piece.mine'),
  };
}"""

# Each drawing and the squares it joins, as the screen has them: an arrow's
# fletching and heart, a serpent's head and the tip of its tail (half way
# round the outline of a body that runs down one side and back up the
# other).
PORTALS = """() => {
  const map = document.getElementById('s69Map');
  const cell = (id) => map.querySelector('.s69-cell[data-id="' + id + '"]').getBoundingClientRect();
  const within = (p, r) => p.x >= r.left - 1 && p.x <= r.right + 1 && p.y >= r.top - 1 && p.y <= r.bottom + 1;
  const middle = (el) => { const r = el.getBoundingClientRect();
                           return {x: r.left + r.width / 2, y: r.top + r.height / 2}; };
  const onScreen = (path, at) => {
    const pt = path.getPointAtLength(at).matrixTransform(path.getScreenCTM());
    return {x: pt.x, y: pt.y};
  };
  const arrows = [...map.querySelectorAll('.s69-arrow')].map(g => {
    const from = Number(g.dataset.from), to = Number(g.dataset.to);
    return {from, to, tail: within(middle(g.querySelector('.s69-feather')), cell(from)),
            head: within(middle(g.querySelector('.s69-heart')), cell(to))};
  });
  const snakes = [...map.querySelectorAll('.s69-snake')].map(g => {
    const from = Number(g.dataset.from), to = Number(g.dataset.to);
    const body = g.querySelector('.s69-body');
    return {from, to, head: within(middle(g.querySelector('.s69-skull')), cell(from)),
            tail: within(onScreen(body, body.getTotalLength() / 2), cell(to))};
  });
  return {arrows, snakes};
}"""

# Every piece that set off on a ride, from the page's first moment: a piece
# leaves its square for the map itself (`.flight`) while it rides.
WATCH_FLIGHTS = """
window.__flights = 0;
new MutationObserver(records => {
  for (const r of records) for (const n of r.addedNodes) {
    if (n.classList && n.classList.contains('s69-piece') && n.classList.contains('flight')) {
      window.__flights += 1;
    }
  }
}).observe(document, {childList: true, subtree: true});
"""


def open_board(player: Player, phones, code: str, **options: Any):
    board = phones(player, start_param=f"s69_{code}", **options)
    board.page.wait_for_selector("#nsfw.show, #s69Board.active")
    if board.page.is_visible("#nsfwYes"):
        board.page.click("#nsfwYes")
    board.screen("s69Board", timeout=POLL)
    board.page.wait_for_selector("#s69Map .s69-cell.here .s69-piece.mine", timeout=POLL)
    return board


def a_game(server: Server, climb_to: int = 0) -> tuple[Player, Player, str]:
    alice, bob = server.player("Alice", paid=True), server.player("Bob")
    code = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})["code"]
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    for _ in range(200):
        state = alice.ok("GET", f"/api/steps69/{code}")
        if state["you"]["position"] >= climb_to:
            break
        (alice if state["your_turn"] else bob).ok("POST", f"/api/steps69/{code}/roll")
    return alice, bob, code


def a_portal_just_fired(server: Server) -> tuple[Player, str, dict[str, Any]]:
    """A game whose last roll landed on an arrow or a serpent. The dice are
    the server's, so roll until one does: seven portals in 69 squares."""
    for _ in range(20):
        alice, bob, code = a_game(server)
        for _ in range(60):
            state = alice.ok("GET", f"/api/steps69/{code}")
            if state["both_home"]:
                break
            mover = alice if state["your_turn"] else bob
            state = mover.ok("POST", f"/api/steps69/{code}/roll")
            if state.get("last", {}).get("event") and not state["both_home"]:
                return alice, code, alice.ok("GET", f"/api/steps69/{code}")
    raise AssertionError("no roll landed on a portal")


def test_the_whole_board_is_in_view_on_a_small_phone_and_a_large_one(
    server: Server, phones
) -> None:
    """Nine columns by eight rows fit a phone whole: the map used to be six
    squares wide, capped at a third of the screen and scrolled to the piece."""
    alice, _, code = a_game(server, climb_to=30)
    board = open_board(alice, phones, code, viewport={"width": 320, "height": 568})
    seen = board.page.evaluate(BOARD_IN_VIEW)
    assert seen == {
        "cells": 69,
        "outside": [],
        "map": True,
        "scrolls": False,
        "dice": True,
        "piece": True,
    }, seen
    board.shot("board-320")
    # A phone turned or a window resized keeps the whole board, piece and all.
    resize(board, {"width": 430, "height": 932})
    assert board.page.evaluate(BOARD_IN_VIEW)["outside"] == []
    assert board.page.evaluate(BOARD_IN_VIEW)["map"] is True
    board.shot("board-430")


def test_every_arrow_and_serpent_joins_its_two_squares(server: Server, phones) -> None:
    """Four Cupid's arrows, fletching on the ladder square and the heart on
    the square it carries you to; three serpents, the head on the snake
    square and the tail on the square it drops you to."""
    alice, _, code = a_game(server)
    board = open_board(alice, phones, code)
    drawn = board.page.evaluate(PORTALS)
    ladders = {(a["from"], a["to"]) for a in drawn["arrows"]}
    snakes = {(s["from"], s["to"]) for s in drawn["snakes"]}
    assert ladders == {(4, 18), (22, 40), (42, 60), (65, 68)}, drawn
    assert snakes == {(13, 2), (35, 20), (55, 38)}, drawn
    for portal in drawn["arrows"] + drawn["snakes"]:
        assert portal["head"] and portal["tail"], portal


def test_a_square_is_a_picture_not_a_button(server: Server, phones) -> None:
    """A tap on a square the piece has not reached used to open its task."""
    alice, _, code = a_game(server)
    board = open_board(alice, phones, code)
    board.tap('#s69Map .s69-cell[data-id="12"]')
    board.page.wait_for_timeout(300)
    assert board.page.evaluate("() => document.querySelectorAll('.overlay.show').length") == 0
    assert "Бархатный путь" not in board.page.inner_text("#s69Board")
    label = board.page.get_attribute("#s69Map", "aria-label") or ""
    assert label.startswith("Поле: ") and "клетка" in label, label


def test_a_piece_rides_the_arrow_or_the_serpent_it_lands_on(server: Server, phones) -> None:
    alice, code, state = a_portal_just_fired(server)
    last = state["last"]
    board = open_board(alice, phones, code, init_script=WATCH_FLIGHTS)
    board.page.wait_for_function("() => window.__flights > 0", timeout=POLL)
    # And it settles where the server put it, the portal's own square left.
    selector = (
        ".s69-piece.mine" if last["seat"] == state["you"]["seat"] else ".s69-piece:not(.mine)"
    )
    board.page.wait_for_function(
        """([sel, to]) => { const p = document.querySelector('#s69Map ' + sel);
                           const cell = p && p.closest('.s69-cell');
                           return !!cell && Number(cell.dataset.id) === to
                                  && !document.querySelector('#s69Map .flight'); }""",
        arg=[selector, last["to"]],
        timeout=POLL,
    )


def test_a_phone_that_asked_for_less_motion_sees_no_ride(server: Server, phones) -> None:
    """D-13: motion that carries meaning ends in the same place, without the
    travel. The piece lands, and then it is where the portal put it."""
    alice, code, state = a_portal_just_fired(server)
    last = state["last"]
    board = open_board(alice, phones, code, reduced_motion=True, init_script=WATCH_FLIGHTS)
    selector = (
        ".s69-piece.mine" if last["seat"] == state["you"]["seat"] else ".s69-piece:not(.mine)"
    )
    board.page.wait_for_function(
        """([sel, to]) => { const p = document.querySelector('#s69Map ' + sel);
                           const cell = p && p.closest('.s69-cell');
                           return !!cell && Number(cell.dataset.id) === to; }""",
        arg=[selector, last["to"]],
        timeout=POLL,
    )
    board.page.wait_for_timeout(700)
    assert board.page.evaluate("() => window.__flights") == 0
