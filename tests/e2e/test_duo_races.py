"""Two thumbs, one instant: the races only a live server can show.

A couple taps at the same moment all the time: both open the invite link as
soon as it arrives, one double-taps the card, both send their fortieth
answer while the other is still reading, both phones poll the moment one of
them has paid. Each of those is a read followed by a write on one shared
row, and the only thing between it and a lost move or two seated guests is
a row lock or a conditional UPDATE.

In-process, one client sends one request after another, so these can only
be tested against a live server. CI runs them on PostgreSQL, the database
production runs (see `.github/workflows/e2e.yml`). They pass against a
server on a SQLite file too, since every transaction there begins
IMMEDIATE (`payments/database.py`). Nine of the ten used to fail there,
when every request shared SQLite's one connection (backend audit B-13).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from vechnost_bot.compat import TOTAL_QUESTIONS
from vechnost_bot.freemium import FREE_CARDS_PER_DECK

from .harness import Player, Server

pytestmark = pytest.mark.live_only

CROWD = 12
DECK = {"theme": "Acquaintance", "level": 1, "type": "questions"}
DECK_SIZE = 30


def statuses(responses: list[Any]) -> Counter[int]:
    return Counter(response.status_code for response in responses)


@pytest.mark.parametrize("path, body", [
    ("/api/rooms", {"theme": "Acquaintance", "level": 1, "type": "questions"}),
    ("/api/compat", None),
    ("/api/steps69", {"mode": "duo", "piece": "hearts"}),
])
def test_a_forwarded_link_opened_by_a_crowd_seats_exactly_one(
    server: Server, path: str, body: Any
) -> None:
    alice = server.player("Alice", paid=True)
    code = alice.ok("POST", path, body)["code"]
    crowd = [server.player(f"Guest{i}") for i in range(CROWD)]
    join_body = {} if path == "/api/steps69" else None
    responses = server.all_at_once(
        [(guest, "POST", f"{path}/{code}/join", join_body) for guest in crowd]
    )
    assert statuses(responses) == Counter({200: 1, 409: CROWD - 1})
    [seated] = [guest for guest, r in zip(crowd, responses, strict=True) if r.status_code == 200]
    assert alice.ok("GET", f"{path}/{code}")["started"] is True
    seated.ok("GET", f"{path}/{code}")
    for guest in crowd:
        if guest is not seated:
            assert guest.status("GET", f"{path}/{code}") == 404


def test_a_double_tap_turns_one_card(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = alice.ok("POST", "/api/rooms", {"theme": "Acquaintance", "level": 1, "type": "questions"})["code"]
    bob.ok("POST", f"/api/rooms/{code}/join")
    responses = server.all_at_once([(alice, "POST", f"/api/rooms/{code}/advance", None)] * 6)
    assert statuses(responses) == Counter({200: 1, 403: 5}), "one tap moved the card, the rest waited"
    after = bob.ok("GET", f"/api/rooms/{code}")
    assert after["idx"] == 1 and after["your_turn"] is True


def test_a_payment_opens_a_finished_room_once_however_many_polls_find_it(
    server: Server,
) -> None:
    """Both phones poll, so the first poll after a purchase is several at
    once, and each finds the room short and a payer in it. One of them deals
    the rest of the deck and carries the pair on to card 6; every other must
    find it dealt. Without the row lock each dealt its own shuffle, the last
    one written won, and the phones were shown different sixth cards.

    Three couples, and each pair polls a while before paying: that is what
    the phones do at the offer screen, and it warms the connection pool - on
    a cold server the first burst queues for connections and never overlaps,
    and a race that does not happen proves nothing.
    """
    for trial in range(3):
        alice = server.player(f"Alice{trial}")
        bob = server.player(f"Bob{trial}")
        code = alice.ok("POST", "/api/rooms", DECK)["code"]
        bob.ok("POST", f"/api/rooms/{code}/join")
        for _ in range(FREE_CARDS_PER_DECK):
            state = alice.ok("GET", f"/api/rooms/{code}")
            (alice if state["your_turn"] else bob).ok("POST", f"/api/rooms/{code}/advance")
        polls = [(player, "GET", f"/api/rooms/{code}", None) for player in (alice, bob)] * (CROWD // 2)
        waiting = [r.json() for r in server.all_at_once(polls)]
        assert all(s["finished"] and s["trimmed"] for s in waiting), "nobody has paid yet"

        server.grant(bob)
        responses = server.all_at_once(polls)
        assert statuses(responses) == Counter({200: CROWD})
        states = [r.json() for r in responses]
        assert {s["idx"] for s in states} == {FREE_CARDS_PER_DECK}, "opened once, on card 6"
        assert {s["finished"] for s in states} == {False}
        assert {s["total"] for s in states} == {DECK_SIZE}
        assert len({s["card_index"] for s in states}) == 1, (
            f"trial {trial}: one deal of the rest, not one per poll"
        )
        sixth = states[0]["card_index"]
        assert alice.ok("GET", f"/api/rooms/{code}")["card_index"] == sixth, "and it is the one that stuck"

    shown = []
    for _ in range(DECK_SIZE - FREE_CARDS_PER_DECK):
        state = alice.ok("GET", f"/api/rooms/{code}")
        shown.append(state["card_index"])
        (alice if state["your_turn"] else bob).ok("POST", f"/api/rooms/{code}/advance")
    assert sorted(shown) == list(range(FREE_CARDS_PER_DECK, DECK_SIZE))


def test_a_double_tap_rolls_the_dice_once(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = alice.ok("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"})["code"]
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    responses = server.all_at_once([(alice, "POST", f"/api/steps69/{code}/roll", None)] * 6)
    assert statuses(responses) == Counter({200: 1, 403: 5})
    state = bob.ok("GET", f"/api/steps69/{code}")
    assert state["partner"]["rolls"] == 1 and state["turn"] == 1


def test_every_answer_in_flight_is_kept(server: Server) -> None:
    """Both partners tapping through the test fast: eighty POSTs at once."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = alice.ok("POST", "/api/compat")["code"]
    bob.ok("POST", f"/api/compat/{code}/join")
    requests: list[tuple[Player, str, str, Any]] = [
        (player, "POST", f"/api/compat/{code}/answer", {"index": i, "value": 1 + (i % 5)})
        for player in (alice, bob) for i in range(TOTAL_QUESTIONS)
    ]
    responses = server.all_at_once(requests)
    assert statuses(responses) == Counter({200: 2 * TOTAL_QUESTIONS})
    for player in (alice, bob):
        state = player.ok("GET", f"/api/compat/{code}")
        assert state["answered"] == TOTAL_QUESTIONS, "an answer went missing"
        assert state["finished"] is True
    assert alice.ok("GET", f"/api/compat/{code}/result") == bob.ok("GET", f"/api/compat/{code}/result")


def test_both_last_answers_at_once_finish_the_test_once(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = alice.ok("POST", "/api/compat")["code"]
    bob.ok("POST", f"/api/compat/{code}/join")
    for index in range(TOTAL_QUESTIONS - 1):
        alice.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 5})
        bob.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 4})
    last = TOTAL_QUESTIONS - 1
    responses = server.all_at_once([
        (alice, "POST", f"/api/compat/{code}/answer", {"index": last, "value": 5}),
        (bob, "POST", f"/api/compat/{code}/answer", {"index": last, "value": 4}),
    ])
    assert statuses(responses) == Counter({200: 2})
    assert any(r.json()["finished"] for r in responses), "whoever landed second finished it"
    for player in (alice, bob):
        assert player.ok("GET", f"/api/compat/{code}")["finished"] is True
        assert player.ok("GET", "/api/compat/mine")["code"] == code


def test_two_different_finales_at_once_the_first_stands(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = alice.ok("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"})["code"]
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    players = {0: alice, 1: bob}
    for _ in range(400):
        state = alice.ok("GET", f"/api/steps69/{code}")
        if state["both_home"]:
            break
        players[state["turn"]].ok("POST", f"/api/steps69/{code}/roll")
    else:
        raise AssertionError("nobody got home")
    choices = [choice["id"] for choice in state["finale"]["choices"]]
    responses = server.all_at_once([
        (alice, "POST", f"/api/steps69/{code}/finale", {"choice": choices[0]}),
        (bob, "POST", f"/api/steps69/{code}/finale", {"choice": choices[1]}),
    ])
    assert statuses(responses) == Counter({200: 1, 409: 1})
    winner = next(r.json()["finale_choice"] for r in responses if r.status_code == 200)
    for player in (alice, bob):
        assert player.ok("GET", f"/api/steps69/{code}")["finale_choice"] == winner


def test_two_purchases_by_a_new_buyer_at_once_are_both_applied(server: Server) -> None:
    """A first-time buyer's two purchases race to create one user row. The
    loser used to be answered 200 "already processed" and never retried
    (9 of 10 trials lost a purchase on PostgreSQL). Now it is told 503, and
    Tribute's redelivery - replayed here - lands.

    Five buyers, after a warm-up: on a cold server the first requests queue
    for a connection and never overlap, and a race that does not happen
    proves nothing.
    """
    warm = [server.webhook_body("unknown_event", Player(server, f"Warm{i}")) for i in range(4)]
    server.deliver_all_at_once(warm)
    for trial in range(5):
        buyer = Player(server, f"Buyer{trial}")
        bodies = [
            server.webhook_body("new_digital_product", buyer, product_id=555),
            server.webhook_body("new_subscription", buyer, subscription_id=777),
        ]
        for body, response in zip(bodies, server.deliver_all_at_once(bodies), strict=True):
            if response.status_code == 503:
                response = server.deliver(body, label="Tribute's retry")
            assert response.status_code == 200, response.text
        for body in bodies:
            again = server.deliver(body, label="redelivery")
            assert "already processed" in again.json()["message"], (
                f"trial {trial}: a purchase was answered 200 and never recorded"
            )
        assert buyer.ok("GET", "/api/questions")["access"]["paid"] is True
