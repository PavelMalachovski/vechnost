"""Couple mode, played by two people: one deck, two phones, taking turns.

Each scenario is what a couple actually does — one opens a room and sends
the link, the other taps it — and checks the thing only two players can
break: that both screens show the same card, that exactly one of them may
turn it, and that a third person holding the link learns nothing.

And what a payment does to a room: a room nobody in it has paid for holds
the free preview, and the moment either of them has access - before the
game or at its last free card - the rest of the deck is dealt in for both.
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
    for key in (
        "code",
        "idx",
        "total",
        "full_total",
        "trimmed",
        "card_index",
        "card_text",
        "finished",
        "started",
        "turn_name",
        "players",
        "theme",
        "level",
        "type",
    ):
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
        assert mover is (alice if step % 2 == 0 else bob), (
            "the creator turns first, then they alternate"
        )
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


def play_to(server: Server, code: str, players: tuple[Player, Player], stop: int) -> None:
    """Turn cards, whoever is on turn, until `stop` cards have been turned."""
    creator, guest = players
    for _ in range(stop):
        state = creator.ok("GET", f"/api/rooms/{code}")
        mover = creator if state["your_turn"] else guest
        mover.ok("POST", f"/api/rooms/{code}/advance")


def test_an_unpaid_couple_plays_the_free_preview_and_is_told_it_is_one(server: Server) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    code = open_room(alice)
    joined = bob.ok("POST", f"/api/rooms/{code}/join")
    assert joined["total"] == FREE_CARDS_PER_DECK
    assert joined["full_total"] == DECK_SIZE
    assert joined["trimmed"] is True, "the app must know to offer the rest, not congratulate"

    play_to(server, code, (alice, bob), FREE_CARDS_PER_DECK)
    a, b = alice.ok("GET", f"/api/rooms/{code}"), bob.ok("GET", f"/api/rooms/{code}")
    assert_same_table(a, b)
    assert a["finished"] is True and a["trimmed"] is True
    assert a["idx"] == FREE_CARDS_PER_DECK - 1


def test_a_paying_guest_opens_an_unpaid_creators_room_for_both(server: Server) -> None:
    """Backend audit B-20: the room used to keep the creator's five cards
    for good, whoever joined it. Either player's access is the room's now."""
    alice = server.player("Alice")
    bob = server.player("Bob", paid=True)
    code = open_room(alice)
    joined = bob.ok("POST", f"/api/rooms/{code}/join")
    assert joined["total"] == DECK_SIZE and joined["trimmed"] is False
    a = alice.ok("GET", f"/api/rooms/{code}")
    assert_same_table(a, joined)

    shown = []
    for _ in range(DECK_SIZE):
        state = alice.ok("GET", f"/api/rooms/{code}")
        shown.append(state["card_index"])
        (alice if state["your_turn"] else bob).ok("POST", f"/api/rooms/{code}/advance")
    assert sorted(shown) == list(range(DECK_SIZE)), "every card of the deck, once"
    assert alice.ok("GET", f"/api/rooms/{code}")["finished"] is True


@pytest.mark.parametrize("payer", ["creator", "guest"])
def test_a_payment_at_the_last_free_card_deals_the_rest_to_both(server: Server, payer: str) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")
    play_to(server, code, (alice, bob), FREE_CARDS_PER_DECK)
    before = alice.ok("GET", f"/api/rooms/{code}")
    assert before["finished"] is True and before["trimmed"] is True

    server.grant(alice if payer == "creator" else bob)

    # The unpaid partner's poll finds it just as the payer's does.
    watcher = bob if payer == "creator" else alice
    b = watcher.ok("GET", f"/api/rooms/{code}")
    a = (alice if watcher is bob else bob).ok("GET", f"/api/rooms/{code}")
    assert_same_table(a, b)
    assert b["finished"] is False, "the room carries on"
    assert b["trimmed"] is False and b["total"] == DECK_SIZE
    assert b["idx"] == FREE_CARDS_PER_DECK, "card 6, not card 1"
    assert b["card_index"] >= FREE_CARDS_PER_DECK, "a card they have not had"
    # The tap that finished the free cards was the creator's (they turn
    # first, and five is odd), so card 6 is the guest's to turn.
    assert b["your_turn"] is (watcher is bob)

    shown = []
    for _ in range(DECK_SIZE - FREE_CARDS_PER_DECK):
        state = alice.ok("GET", f"/api/rooms/{code}")
        shown.append(state["card_index"])
        (alice if state["your_turn"] else bob).ok("POST", f"/api/rooms/{code}/advance")
    assert sorted(shown) == list(range(FREE_CARDS_PER_DECK, DECK_SIZE)), (
        "the rest of the deck, each card once, none of the free ones again"
    )
    assert alice.ok("GET", f"/api/rooms/{code}")["finished"] is True


def test_a_payment_in_the_middle_of_the_free_cards_keeps_the_card_on_the_table(
    server: Server,
) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")
    play_to(server, code, (alice, bob), 2)
    before = bob.ok("GET", f"/api/rooms/{code}")
    server.grant(bob)
    after = alice.ok("GET", f"/api/rooms/{code}")
    assert after["total"] == DECK_SIZE and after["trimmed"] is False
    for key in ("idx", "card_index", "card_text", "turn_name"):
        assert after[key] == before[key], f"a payment moved {key}"
    # The free cards still to come keep their places; the rest follow them.
    play_to(server, code, (alice, bob), FREE_CARDS_PER_DECK - 2)
    sixth = alice.ok("GET", f"/api/rooms/{code}")
    assert sixth["idx"] == FREE_CARDS_PER_DECK and sixth["card_index"] >= FREE_CARDS_PER_DECK


def test_somebody_elses_payment_does_not_open_the_room(server: Server) -> None:
    """A third person's access is not the room's: only its two players count,
    and a stranger who is refused the seat changes nothing by asking."""
    alice = server.player("Alice")
    bob = server.player("Bob")
    carol = server.player("Carol", paid=True)
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")
    assert carol.status("POST", f"/api/rooms/{code}/join") == 409
    for player in (alice, bob):
        state = player.ok("GET", f"/api/rooms/{code}")
        assert state["total"] == FREE_CARDS_PER_DECK and state["trimmed"] is True


def test_neither_partner_can_take_a_card_out_of_the_room(server: Server) -> None:
    """The share button rendered the card on the table as a picture to save
    or send, and in a paid room the partner who did not pay could take any
    card the room had dealt them. Both went: the cards stay in the game."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")
    idx = bob.ok("GET", f"/api/rooms/{code}")["card_index"]
    card = f"/api/card?theme=Acquaintance&level=1&type=questions&idx={idx}"

    assert alice.status("GET", card) == 404
    assert bob.status("GET", f"{card}&room={code}") == 404


def test_an_18_plus_room_seats_nobody_who_has_not_said_they_are_18(server: Server) -> None:
    """The app asks before the guest's first card of the Sex deck. The seat
    stays empty until they say yes (`nsfw=1`), so a partner who says no is
    not left sitting in a room the creator then plays alone."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_room(alice, {"theme": "Sex", "level": None, "type": "tasks"})
    assert alice.ok("GET", f"/api/rooms/{code}")["nsfw"] is True
    assert bob.status("POST", f"/api/rooms/{code}/join") == 403
    assert alice.ok("GET", f"/api/rooms/{code}")["started"] is False, "the seat is still free"
    joined = bob.ok("POST", f"/api/rooms/{code}/join?nsfw=1")
    assert joined["started"] is True and joined["your_role"] == "guest"
    # Once seated, opening the link again is not asked twice.
    assert bob.ok("POST", f"/api/rooms/{code}/join")["your_role"] == "guest"
    # Nor is the creator, who chose the deck; nor anyone at a deck that is not 18+.
    assert alice.ok("POST", f"/api/rooms/{code}/join")["your_role"] == "creator"
    plain = open_room(alice)
    assert alice.ok("GET", f"/api/rooms/{plain}")["nsfw"] is False
    assert server.player("Carol").ok("POST", f"/api/rooms/{plain}/join")["started"] is True


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
    """Two phones behind one router share one address, not one budget."""
    alice = server.player("Alice", paid=True, ip="198.18.7.7")
    bob = server.player("Bob", ip="198.18.7.7")
    code = open_room(alice)
    bob.ok("POST", f"/api/rooms/{code}/join")
    players = [alice, bob]
    for step in range(DECK_SIZE):
        players[step % 2].ok("POST", f"/api/rooms/{code}/advance")
        players[(step + 1) % 2].ok("GET", f"/api/rooms/{code}")
    assert bob.ok("GET", f"/api/rooms/{code}")["finished"] is True


def test_a_stranger_behind_the_same_carrier_nat_does_not_lock_the_partner_out(
    server: Server,
) -> None:
    """A mobile carrier puts strangers behind one public address. Carol
    spends her whole `join` budget guessing codes; Bob, on the same address,
    still opens Alice's link, because the budget is Carol's, not the
    address's."""
    from vechnost_bot.payments import throttle

    nat = "100.64.10.10"
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob", ip=nat)
    carol = server.player("Carol", ip=nat)
    code = open_room(alice)

    limit, _ = throttle.LIMITS["join"]
    guesses = [
        carol.status("POST", f"/api/rooms/{invites.new_code()}/join") for _ in range(limit + 1)
    ]
    assert guesses[:limit] == [404] * limit and guesses[-1] == 429

    joined = bob.ok("POST", f"/api/rooms/{code}/join")
    assert joined["started"] is True and joined["your_role"] == "guest"


def test_stale_initdata_is_refused(server: Server) -> None:
    """A phone left open for two days re-authenticates rather than plays on."""
    stale = Player(server, "Sleepy", auth_date=1_600_000_000)
    assert stale.status("POST", "/api/rooms", DECK) == 401


@pytest.mark.parametrize(
    "deck",
    [
        {"theme": "For Couples", "level": 3, "type": "questions"},
        {"theme": "Sex", "type": "tasks"},
        {"theme": "Provocation", "type": "questions"},
    ],
)
def test_every_deck_opens_for_two(server: Server, deck: dict[str, Any]) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_room(alice, {"level": None, **deck})
    b = bob.ok("POST", f"/api/rooms/{code}/join?nsfw=1")
    a = alice.ok("GET", f"/api/rooms/{code}")
    assert_same_table(a, b)
    assert a["total"] > FREE_CARDS_PER_DECK and a["card_text"]
