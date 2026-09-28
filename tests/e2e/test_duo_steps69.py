"""«69 ступеней», played to the end by two people on two phones.

Two pieces, two positions, one die the server throws. What only two
players can break, and what every scenario here checks at every turn:

* both phones agree on where both pieces stand and whose turn it is;
* only the player on turn can roll, and a refused roll moves nothing;
* every move is the one the rules say (`steps69.resolve_move`), portals and
  the cap at 69 included, and the turn passes the way it should — skipping
  a partner who is already home;
* a deal reaches exactly one player: a secret's instruction and a Joker's
  task never appear anywhere in the partner's payload.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from vechnost_bot import invites, steps69

from .harness import LeakDetected, Player, Server, code_from_invite

PIECES = {"hearts", "spades", "clubs", "diamonds"}
BOARD = steps69.BOARD_SIZE
# A game is ~20 rolls a piece; this bound only exists so a broken turn
# order fails instead of looping.
MAX_ROLLS = 400

SECRETS = {c.id: c.secret for c in steps69.load_cells() if c.kind == "secret"}
JOKER_TEXTS = {t.id: t.text for tasks in steps69.load_jokers().values() for t in tasks}


def open_game(creator: Player, piece: str = "hearts") -> str:
    state = creator.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": piece})
    assert state["started"] is False and state["your_turn"] is False
    assert state["you"]["piece"] == piece and state["you"]["position"] == 1
    code = code_from_invite(state["invite_url"])
    assert code == state["code"] and invites.valid_code(code)
    return code


def assert_same_board(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Alice's "you" is Bob's "partner", and the other way round."""
    for key in (
        "code",
        "mode",
        "started",
        "finished",
        "turn",
        "turn_name",
        "both_home",
        "finale_choice",
    ):
        assert a[key] == b[key], f"the partners disagree on {key!r}: {a[key]!r} vs {b[key]!r}"
    for mine, theirs in ((a["you"], b["partner"]), (a["partner"], b["you"])):
        for key in ("seat", "piece", "position", "rolls", "home"):
            assert mine[key] == theirs[key], f"the partners disagree on {key!r}"
    assert a["you"]["piece"] != a["partner"]["piece"], "two players never wear one suit"
    if a["started"] and not a["finished"] and not a["both_home"]:
        assert a["your_turn"] != b["your_turn"], "exactly one partner may roll"
    if "last" in a or "last" in b:
        assert a.get("last") == b.get("last"), "both phones show the same last move"


def assert_deals_stay_private(
    viewer: str, body: dict[str, Any], mine: int, theirs: int, their_joker: str | None
) -> None:
    """Nothing dealt to the partner is in the viewer's payload.

    Unless the viewer stands on the very same square: then the instruction
    is the viewer's own deal too.
    """
    partner_cell = body["partner"]["cell"]
    if partner_cell.get("secret") or partner_cell.get("joker") or partner_cell.get("text"):
        raise LeakDetected(f"{viewer} sees the partner's cell as the mover does: {partner_cell}")
    text = json.dumps(body, ensure_ascii=False)
    if theirs != mine and theirs in SECRETS and SECRETS[theirs] in text:
        raise LeakDetected(f"{viewer} received the partner's secret on cell {theirs}")
    if their_joker and their_joker in text:
        raise LeakDetected(f"{viewer} received the partner's Joker task")


def play_to_the_end(server: Server, code: str, players: dict[int, Player]) -> dict[str, Any]:
    """Alternate rolls until both pieces are home, checking every turn."""
    path = f"/api/steps69/{code}?lang=ru"
    jokers: dict[int, str | None] = {0: None, 1: None}
    dealt: list[str] = []
    for rolls in range(MAX_ROLLS):
        views = {seat: player.ok("GET", path) for seat, player in players.items()}
        assert_same_board(views[0], views[1])
        positions = {seat: views[seat]["you"]["position"] for seat in players}
        for seat, view in views.items():
            assert 1 <= positions[seat] <= BOARD
            assert_deals_stay_private(
                players[seat].name, view, positions[seat], positions[1 - seat], jokers[1 - seat]
            )
        if views[0]["both_home"]:
            return views[0]

        mover = views[0]["turn"]
        waiter = 1 - mover
        assert views[mover]["your_turn"] and not views[waiter]["your_turn"]
        if rolls % 4 == 0:
            # Out of turn: refused, and nothing moves. A partner already home
            # is told the dice are done, not to wait for a turn.
            refused = 409 if positions[waiter] >= BOARD else 403
            assert players[waiter].status("POST", f"/api/steps69/{code}/roll") == refused
        after = players[mover].ok("POST", f"/api/steps69/{code}/roll?lang=ru")

        last = after["last"]
        expected = steps69.resolve_move(positions[mover], last["roll"])
        assert last["seat"] == mover and last["from"] == positions[mover]
        assert 1 <= last["roll"] <= 6
        assert (last["landed"], last["to"], last["event"]) == (
            expected.landed,
            expected.position,
            expected.event,
        ), f"a roll of {last['roll']} from {positions[mover]} went wrong"
        assert after["you"]["position"] == expected.position
        assert after["you"]["rolls"] == views[mover]["you"]["rolls"] + 1
        partner_home = positions[waiter] >= BOARD
        assert after["turn"] == (mover if partner_home else waiter), "the turn passed wrongly"

        cell = after["you"]["cell"]
        if cell["kind"] == "joker":
            assert cell["joker"], "a Joker square deals a task to whoever lands on it"
            jokers[mover] = cell["joker"]["text"]
            dealt.append(cell["joker"]["id"])
        else:
            jokers[mover] = None
        if cell["kind"] == "secret":
            assert cell["secret"] == SECRETS[cell["id"]], "the mover reads their secret"
    raise AssertionError(f"nobody got home in {MAX_ROLLS} rolls")


@pytest.mark.parametrize("round_", range(3))
def test_two_phones_play_to_the_finale(server: Server, round_: int) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")  # plays free on Alice's game
    code = open_game(alice, piece="hearts")
    assert alice.status("POST", f"/api/steps69/{code}/roll") == 409, "nobody rolls alone"

    # The ordinary invite: Bob never touched the suit picker.
    joined = bob.ok("POST", f"/api/steps69/{code}/join?lang=ru", {})
    assert joined["started"] is True and joined["your_role"] == "guest"
    assert joined["you"]["piece"] in PIECES - {"hearts"}

    board = bob.ok("GET", f"/api/steps69/{code}/board?lang=ru")
    board_text = json.dumps(board, ensure_ascii=False)
    for secret in SECRETS.values():
        assert secret not in board_text, "the printed board carries no secret"
    for task in JOKER_TEXTS.values():
        assert task not in board_text, "the printed board carries no Joker task"
    assert len(board["cells"]) == BOARD

    choice_id = steps69.load_finale().choices[0].id
    assert bob.status("POST", f"/api/steps69/{code}/finale", {"choice": choice_id}) == 409
    for player in (alice, bob):
        assert player.ok("GET", "/api/steps69/mine")["code"] == code

    final = play_to_the_end(server, code, {0: alice, 1: bob})
    assert final["finale"] and final["finished"] is False
    for player in (alice, bob):
        assert player.status("POST", f"/api/steps69/{code}/roll") == 409, "home blocks the dice"

    other = steps69.load_finale().choices[1].id
    done = bob.ok("POST", f"/api/steps69/{code}/finale?lang=ru", {"choice": choice_id})
    assert done["finished"] is True and done["finale_choice"] == choice_id
    # Both tap at once: the first choice stands, a repeat is harmless.
    assert alice.status("POST", f"/api/steps69/{code}/finale", {"choice": other}) == 409
    assert alice.ok("POST", f"/api/steps69/{code}/finale", {"choice": choice_id})["finished"]
    for player in (alice, bob):
        assert player.status("GET", "/api/steps69/mine") == 404, "a finished game is not resumable"
    assert_same_board(
        alice.ok("GET", f"/api/steps69/{code}"), bob.ok("GET", f"/api/steps69/{code}")
    )


def test_a_clashing_suit_is_swapped_not_refused(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_game(alice, piece="spades")
    joined = bob.ok("POST", f"/api/steps69/{code}/join", {"piece": "spades"})
    assert joined["you"]["piece"] in PIECES - {"spades"}
    assert sorted(joined["pieces_taken"]) == sorted({"spades", joined["you"]["piece"]})


def test_an_unpaid_creator_cannot_open_a_board(server: Server) -> None:
    alice = server.player("Alice")
    assert alice.status("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"}) == 402


def test_a_refund_mid_game_does_not_strand_the_couple(server: Server) -> None:
    """Access is checked when the board opens; a game in flight plays on.

    What the rule is today, pinned so that changing it is a decision: the
    couple finishes the evening, and the refunded creator cannot open the
    next board.
    """
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_game(alice)
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    alice.ok("POST", f"/api/steps69/{code}/roll")
    server.revoke(alice)
    bob.ok("POST", f"/api/steps69/{code}/roll")
    alice.ok("POST", f"/api/steps69/{code}/roll")
    assert alice.status("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"}) == 402


def test_a_stranger_cannot_find_or_touch_the_board(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    carol = server.player("Carol", paid=True)
    code = open_game(alice)
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    alice.ok("POST", f"/api/steps69/{code}/roll")

    nobody = invites.new_code()
    probes: list[tuple[str, str, Any]] = [
        ("GET", "", None),
        ("GET", "/board", None),
        ("POST", "/roll", None),
        ("POST", "/finale", {"choice": "sync"}),
        ("DELETE", "", None),
    ]
    for method, suffix, body in probes:
        live = carol.call(method, f"/api/steps69/{code}{suffix}", json_body=body)
        dead = carol.call(method, f"/api/steps69/{nobody}{suffix}", json_body=body)
        assert live.status_code == dead.status_code == 404, (method, suffix)
        assert live.json() == dead.json()
    assert carol.status("POST", f"/api/steps69/{code}/join", {}) == 409
    assert carol.status("GET", "/api/steps69/mine") == 404
    assert alice.ok("GET", f"/api/steps69/{code}")["partner"]["rolls"] == 0


def test_either_partner_can_erase_the_board(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_game(alice)
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    alice.ok("POST", f"/api/steps69/{code}/roll")
    assert bob.ok("DELETE", f"/api/steps69/{code}") == {"deleted": True}
    for player in (alice, bob):
        assert player.status("GET", f"/api/steps69/{code}") == 404
        assert player.status("POST", f"/api/steps69/{code}/roll") == 404
        assert player.status("GET", "/api/steps69/mine") == 404


def test_one_phone_passed_back_and_forth(server: Server) -> None:
    """The solo board: one device, both seats, nobody else may sit down."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob", paid=True)
    state = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "solo", "piece": "diamonds"})
    code = state["code"]
    assert state["started"] is True and state["your_turn"] is True
    assert bob.status("POST", f"/api/steps69/{code}/join", {}) == 409

    seats = []
    for _ in range(6):
        after = alice.ok("POST", f"/api/steps69/{code}/roll?lang=ru")
        seats.append(after["last"]["seat"])
        # One phone shows the seat that just moved, with everything dealt.
        assert after["you"]["seat"] == after["last"]["seat"]
        assert after["you"]["position"] == after["last"]["to"]
    assert seats == [0, 1, 0, 1, 0, 1], "the seats alternate on one phone"
