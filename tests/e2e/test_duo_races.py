"""Two thumbs, one instant: the races only a live server can show.

A couple taps at the same moment all the time: both open the invite link as
soon as it arrives, one double-taps the card, both send their fortieth
answer while the other is still reading. Each of those is a read followed by
a write on one shared row, and the only thing between it and a lost move or
two seated guests is a row lock or a conditional UPDATE.

In-process, one client sends one request after another, so these can only
be tested against a live server — and they mean something only on the
database production runs. CI runs them on PostgreSQL (see
`.github/workflows/e2e.yml`); SQLite's single shared connection cannot keep
any of these promises (backend audit B-13), so they are not run there.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from vechnost_bot.compat import TOTAL_QUESTIONS

from .harness import Player, Server

pytestmark = pytest.mark.live_only

CROWD = 12


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
