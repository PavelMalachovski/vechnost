"""The compatibility test, taken by two people on two phones.

Forty questions each, answered apart and compared. What only two players
can break: the result both partners read must be the same one, computed
from both answer sets, and neither partner may ever be shown what the
other one answered — not in the result, not in a progress poll, not in a
404's body.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from vechnost_bot import invites
from vechnost_bot.compat import TOTAL_QUESTIONS, build_result
from vechnost_bot.i18n import get_text

from .harness import (
    LeakDetected,
    Player,
    Server,
    code_from_invite,
    keys_in,
)

# Every key the result may carry. A key added to the result has to be added
# here too, by someone who has decided it does not let one partner work out
# the other's answers (CLAUDE.md: "no per-sphere score").
RESULT_KEYS = {
    "percent",
    "spheres",
    "strengths",
    "strengths_fallback",
    "attention",
    "divergent_all",
    "questions",
    "recommendation",
    "critical_blocks",
    "id",
    "title",
    "zone",
    "verdict",
    "divergent",
    "sphere",
    "framing",
}
# The same for a progress poll: counts, never values.
STATE_KEYS = {
    "code",
    "your_role",
    "started",
    "answered",
    "answered_indices",
    "partner_answered",
    "total",
    "finished",
    "players",
    "creator",
    "guest",
    "invite_url",
}
FORBIDDEN_KEYS = {
    "creator_answers",
    "guest_answers",
    "answers",
    "score",
    "scores",
    "avg",
    "average",
}


def open_test(creator: Player) -> str:
    state = creator.ok("POST", "/api/compat?lang=ru")
    assert state["your_role"] == "creator" and state["started"] is False
    code = code_from_invite(state["invite_url"])
    assert code == state["code"] and invites.valid_code(code)
    return code


def answer_all(code: str, answers: dict[Player, list[int]], rng: random.Random) -> None:
    """Both partners answer, interleaved the way two phones would be."""
    queue = [(player, index) for player in answers for index in range(TOTAL_QUESTIONS)]
    rng.shuffle(queue)
    done = dict.fromkeys(answers, 0)
    partner = dict(zip(answers, reversed(list(answers)), strict=True))
    for step, (player, index) in enumerate(queue):
        state = player.ok(
            "POST",
            f"/api/compat/{code}/answer",
            {"index": index, "value": answers[player][index]},
        )
        done[player] += 1
        assert STATE_KEYS >= keys_in(state), f"new key in state: {keys_in(state) - STATE_KEYS}"
        assert state["answered"] == done[player]
        assert state["partner_answered"] == done[partner[player]]
        assert index in state["answered_indices"]
        if step < len(queue) - 1:
            assert state["finished"] is False
            # Nobody reads a result until both have finished.
            assert player.status("GET", f"/api/compat/{code}/result") == 409
    assert all(count == TOTAL_QUESTIONS for count in done.values())


def assert_no_answers_leaked(server: Server, answers: dict[Player, list[int]]) -> None:
    """No body either partner received may carry an answer set or a score."""
    for exchange in server.transcript.exchanges:
        if exchange.who not in {p.name for p in answers}:
            continue
        body = exchange.received
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        found = FORBIDDEN_KEYS & keys_in(body)
        if found:
            raise LeakDetected(f"{exchange.method} {exchange.path} carried {found}")
        for player, values in answers.items():
            if player.name == exchange.who:
                continue
            # The partner's forty answers, in any JSON spelling of a list.
            for spelling in (json.dumps(values), json.dumps(values, separators=(",", ":"))):
                if spelling in text:
                    raise LeakDetected(f"{exchange.who} received {player.name}'s answers")


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_two_partners_take_the_test_and_read_one_result(server: Server, seed: int) -> None:
    rng = random.Random(seed)
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_test(alice)

    # Nobody answers into a test the partner has not joined.
    assert alice.status("POST", f"/api/compat/{code}/answer", {"index": 0, "value": 3}) == 409

    joined = bob.ok("POST", f"/api/compat/{code}/join?lang=ru")
    assert joined["your_role"] == "guest" and joined["started"] is True

    answers = {
        alice: [rng.randint(1, 5) for _ in range(TOTAL_QUESTIONS)],
        bob: [rng.randint(1, 5) for _ in range(TOTAL_QUESTIONS)],
    }
    answer_all(code, answers, rng)

    a = alice.ok("GET", f"/api/compat/{code}/result?lang=ru")
    b = bob.ok("GET", f"/api/compat/{code}/result?lang=ru")
    assert a == b, "both partners read one result"
    expected = json.loads(build_result(answers[alice], answers[bob]).model_dump_json())
    assert a == expected, "the server's result is the domain's result for these answers"
    assert RESULT_KEYS >= keys_in(a), f"new key in result: {keys_in(a) - RESULT_KEYS}"

    # A completed test is immutable, for both.
    for player in (alice, bob):
        assert player.status("POST", f"/api/compat/{code}/answer", {"index": 0, "value": 5}) == 409
    # And it is what each of them is shown as "my last result".
    for player in (alice, bob):
        mine = player.ok("GET", "/api/compat/mine?lang=ru")
        assert mine["code"] == code and mine["result"] == a

    assert_no_answers_leaked(server, answers)


@pytest.mark.inprocess_only
def test_both_partners_are_told_the_result_is_ready(server: Server) -> None:
    """The second partner often finishes hours later; the push is how the
    first one finds out. Exactly one each, and not before the end."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_test(alice)
    bob.ok("POST", f"/api/compat/{code}/join")
    ready = get_text("compat.ready")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 4})
    for index in range(TOTAL_QUESTIONS - 1):
        bob.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 2})
    assert ready not in server.telegram.texts_to(alice.id), "no push before both finish"
    bob.ok("POST", f"/api/compat/{code}/answer", {"index": TOTAL_QUESTIONS - 1, "value": 2})

    for player in (alice, bob):
        pushes = [text for text in server.telegram.texts_to(player.id) if text == ready]
        assert len(pushes) == 1, f"{player.name} got {len(pushes)} result pushes"
        button = server.telegram.to(player.id)[-1].buttons()[0]
        assert "web_app" in button, "the push opens the Mini App, where initData exists"


def test_changing_an_answer_does_not_count_twice(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_test(alice)
    bob.ok("POST", f"/api/compat/{code}/join")
    for value in (1, 5, 3):
        state = alice.ok("POST", f"/api/compat/{code}/answer", {"index": 7, "value": value})
        assert state["answered"] == 1 and state["answered_indices"] == [7]
    assert bob.ok("GET", f"/api/compat/{code}")["partner_answered"] == 1


def test_either_partner_can_erase_the_test_for_both(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_test(alice)
    bob.ok("POST", f"/api/compat/{code}/join")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 3})
        bob.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 3})

    assert bob.ok("DELETE", f"/api/compat/{code}") == {"deleted": True}
    for player in (alice, bob):
        assert player.status("GET", f"/api/compat/{code}") == 404
        assert player.status("GET", f"/api/compat/{code}/result") == 404
        assert player.ok("GET", "/api/compat/mine") is None


def test_a_retake_replaces_the_previous_result(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    first = open_test(alice)
    bob.ok("POST", f"/api/compat/{first}/join")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{first}/answer", {"index": index, "value": 5})
        bob.ok("POST", f"/api/compat/{first}/answer", {"index": index, "value": 1})

    # Months later, Bob opens the retake and Alice joins it.
    bob_paid = server.player("Bob", telegram_id=bob.id, ip=bob.ip, paid=True)
    second = open_test(bob_paid)
    alice.ok("POST", f"/api/compat/{second}/join")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{second}/answer", {"index": index, "value": 4})
        bob_paid.ok("POST", f"/api/compat/{second}/answer", {"index": index, "value": 4})

    for player in (alice, bob_paid):
        assert player.ok("GET", "/api/compat/mine")["code"] == second
        assert player.status("GET", f"/api/compat/{first}") == 404, "the old answers are gone"


def test_finishing_an_older_test_does_not_delete_a_retake_in_progress(server: Server) -> None:
    """Two tests open for one pair - a second invite sent by mistake, say.
    Completing the older one used to delete the newer one outright, and the
    partner halfway through it got a 404 on their next answer."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob", paid=True)
    older = open_test(alice)
    bob.ok("POST", f"/api/compat/{older}/join")
    for index in range(TOTAL_QUESTIONS - 1):
        alice.ok("POST", f"/api/compat/{older}/answer", {"index": index, "value": 4})
        bob.ok("POST", f"/api/compat/{older}/answer", {"index": index, "value": 4})
    newer = open_test(bob)
    alice.ok("POST", f"/api/compat/{newer}/join")
    for index in range(10):
        bob.ok("POST", f"/api/compat/{newer}/answer", {"index": index, "value": 2})

    last = TOTAL_QUESTIONS - 1
    alice.ok("POST", f"/api/compat/{older}/answer", {"index": last, "value": 4})
    bob.ok("POST", f"/api/compat/{older}/answer", {"index": last, "value": 4})
    assert bob.ok("GET", f"/api/compat/{newer}")["answered"] == 10, "the retake survived"
    bob.ok("POST", f"/api/compat/{newer}/answer", {"index": 10, "value": 2})

    # Finishing the retake supersedes the older one.
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{newer}/answer", {"index": index, "value": 3})
    for index in range(11, TOTAL_QUESTIONS):
        bob.ok("POST", f"/api/compat/{newer}/answer", {"index": index, "value": 2})
    assert alice.status("GET", f"/api/compat/{older}") == 404
    assert alice.ok("GET", "/api/compat/mine")["code"] == newer


def test_an_unpaid_creator_is_asked_to_pay(server: Server) -> None:
    alice = server.player("Alice")
    assert alice.status("POST", "/api/compat") == 402


def test_a_stranger_cannot_tell_the_test_exists(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    carol = server.player("Carol", paid=True)
    code = open_test(alice)
    bob.ok("POST", f"/api/compat/{code}/join")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 2})
        bob.ok("POST", f"/api/compat/{code}/answer", {"index": index, "value": 4})

    nobody = invites.new_code()
    probes: list[tuple[str, str, Any]] = [
        ("GET", "", None),
        ("GET", "/result", None),
        ("POST", "/answer", {"index": 0, "value": 1}),
        ("DELETE", "", None),
    ]
    for method, suffix, body in probes:
        live = carol.call(method, f"/api/compat/{code}{suffix}", json_body=body)
        dead = carol.call(method, f"/api/compat/{nobody}{suffix}", json_body=body)
        assert live.status_code == dead.status_code == 404, (method, suffix)
        assert live.json() == dead.json()
    assert carol.status("POST", f"/api/compat/{code}/join") == 409
    # The test survived the stranger's DELETE.
    assert alice.ok("GET", f"/api/compat/{code}")["finished"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"index": -1, "value": 3},
        {"index": TOTAL_QUESTIONS, "value": 3},
        {"index": 0, "value": 0},
        {"index": 0, "value": 6},
        {"index": "zero", "value": 3},
        {"value": 3},
    ],
)
def test_a_malformed_answer_is_refused_not_crashed(server: Server, body: dict[str, Any]) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    code = open_test(alice)
    bob.ok("POST", f"/api/compat/{code}/join")
    assert alice.status("POST", f"/api/compat/{code}/answer", body) == 422
    assert alice.ok("GET", f"/api/compat/{code}")["answered"] == 0
