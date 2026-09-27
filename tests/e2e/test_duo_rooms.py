"""Couple mode, played by two people: one deck, two phones, taking turns.

Each scenario is what a couple actually does — one opens a room and sends
the link, the other taps it — and checks the thing only two players can
break: that both screens show the same card, that exactly one of them may
turn it, and that a third person holding the link learns nothing.
"""

from __future__ import annotations

from typing import Any

import pytest

from vechnost_bot import invites
from vechnost_bot.freemium import FREE_CARDS_PER_DECK

from .harness import Player, Server, code_from_invite

DECK = {"theme": "Acquaintance", "level": 1, "type": "questions"}
DECK_SIZE = 30  # data/questions.yaml, Acquaintance level 1


def open_room(creator: Player, deck: dict[str, Any] = DECK) -> str:
    """The creator opens a room and reads the code out of the invite link."""
    state = creator.ok("POST", "/api/rooms?lang=ru", deck)
    assert state["your_role"] == "creator"
    assert state["started"] is False and state["your_turn"] is False
    code = code_from_invite(state["invite_url"])
    assert code == state["code"]
    assert invites.valid_code(code)
    return code


def assert_same_table(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Two phones looking at one room must agree on everything but whose they are."""
    for key in ("code", "idx", "total", "card_index", "card_text", "finished",
                "started", "turn_name", "players", "theme", "level", "type"):
        assert a[key] == b[key], f"the partners disagree on {key!r}: {a[key]!r} vs {b[key]!r}"
    assert {a["your_role"], b["your_role"]} == {"creator", "guest"}
    if a["started"] and not a["finished"]:
        assert a["your_turn"] != b["your_turn"], "exactly one partner may turn the card"
    else:
        assert not a["your_turn"] and not b["your_turn"]


def test_paid_creator_and_unpaid_guest_play_the_whole_deck(server: Server) -> None:
    """The ordinary evening: she paid, he didn't, the room covers both."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_room(alice)

    joined = bob.ok("POST", f"/api/rooms/{code}/join?lang=ru")
    assert joined["your_role"] == "guest" and joined["started"] is True
    assert joined["total"] == DECK_SIZE, "a paid creator's room is the whole deck"

    shown: list[int] = []
    for step in range(DECK_SIZE):
        a = alice.ok("GET", f"/api/rooms/{code}?lang=ru")
        b = bob.ok("GET", f"/api/rooms/{code}?lang=ru")
        assert_same_table(a, b)
        assert a["card_text"], "every card has a text"
        assert a["idx"] == step
        shown.append(a["card_index"])

        mover, waiter = (alice, bob) if a["your_turn"] else (bob, alice)
        assert mover is (alice if step % 2 == 0 else bob), "the creator turns first, then they alternate"
        # Out of turn: refused, and nothing moves.
        assert waiter.status("POST", f"/api/rooms/{code}/advance") == 403
        assert alice.ok("GET", f"/api/rooms/{code}")["idx"] == step
        mover.ok("POST", f"/api/rooms/{code}/advance?lang=ru")

    assert sorted(shown) == list(range(DECK_SIZE)), "every card exactly once"
    a = alice.ok("GET", f"/api/rooms/{code}")
    b = bob.ok("GET", f"/api/rooms/{code}")
    assert a["finished"] and b["finished"]
    assert_same_table(a, b)
    for player in (alice, bob):
        assert player.status("POST", f"/api/rooms/{code}/advance") == 409


def test_an_unpaid_creator_shares_the_free_preview_only(server: Server) -> None:
    """The room inherits the creator's access at creation, and only that.

    Documented rule (CLAUDE.md, rooms.py): a paying guest in an unpaid
    creator's room still gets the preview. Pinned here so a change to it is
    a decision, not an accident.
    """
    alice = server.player("Alice")
    bob = server.player("Bob", paid=True)
    code = open_room(alice)
    joined = bob.ok("POST", f"/api/rooms/{code}/join")
    assert joined["total"] == FREE_CARDS_PER_DECK
    assert alice.ok("GET", f"/api/rooms/{code}")["total"] == FREE_CARDS_PER_DECK


def test_a_third_person_with_the_link_learns_nothing(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    carol = server.player("Carol", paid=True)
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")

    # The seat is taken; join is throttled, so its 409 is not an oracle.
    assert carol.status("POST", f"/api/rooms/{code}/join") == 409
    # Every other door answers exactly as a code nobody minted would.
    nobody = invites.new_code()
    for method, suffix in (("GET", ""), ("POST", "/advance")):
        live = carol.call(method, f"/api/rooms/{code}{suffix}")
        dead = carol.call(method, f"/api/rooms/{nobody}{suffix}")
        assert live.status_code == dead.status_code == 404
        assert live.json() == dead.json()
    # And the couple did not notice.
    assert_same_table(alice.ok("GET", f"/api/rooms/{code}"), bob.ok("GET", f"/api/rooms/{code}"))


def test_the_creator_reopening_their_own_link_stays_the_creator(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    code = open_room(alice)
    again = alice.ok("POST", f"/api/rooms/{code}/join")
    assert again["your_role"] == "creator" and again["started"] is False
    assert alice.status("POST", f"/api/rooms/{code}/advance") == 409


def test_a_couple_on_one_home_wifi_can_play(server: Server) -> None:
    """Two phones behind one router share one address, and one budget."""
    alice = server.player("Alice", paid=True, ip="198.18.7.7")
    bob = server.player("Bob", ip="198.18.7.7")
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")
    players = [alice, bob]
    for step in range(DECK_SIZE):
        players[step % 2].ok("POST", f"/api/rooms/{code}/advance")
        players[(step + 1) % 2].ok("GET", f"/api/rooms/{code}")
    assert bob.ok("GET", f"/api/rooms/{code}")["finished"] is True


def test_stale_initdata_is_refused(server: Server) -> None:
    """A phone left open for two days re-authenticates rather than plays on."""
    stale = Player(server, "Sleepy", auth_date=1_600_000_000)
    assert stale.status("POST", "/api/rooms", DECK) == 401


@pytest.mark.parametrize("deck", [
    {"theme": "For Couples", "level": 3, "type": "questions"},
    {"theme": "Sex", "type": "tasks"},
    {"theme": "Provocation", "type": "questions"},
])
def test_every_deck_opens_for_two(server: Server, deck: dict[str, Any]) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_room(alice, {"level": None, **deck})
    b = bob.ok("POST", f"/api/rooms/{code}/join")
    a = alice.ok("GET", f"/api/rooms/{code}")
    assert_same_table(a, b)
    assert a["total"] > FREE_CARDS_PER_DECK and a["card_text"]
