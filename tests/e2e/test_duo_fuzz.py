"""Three people doing anything, in any order — checked against the rules.

The scenario suites test the paths someone thought of. This machine tests
the ones nobody did. Hypothesis drives three Telegram users through random
interleavings of every two-partner action the Mini App can send:

* Alice, who paid;
* Bob, who did not (and plays on whatever Alice opens) - until, perhaps,
  the middle of a game in a room of his own, when he buys access;
* Carol, who paid too, and who may get hold of anybody's link.

They create, join, poll, answer, roll, choose finales and delete — rooms,
compatibility tests and «69 ступеней» boards, their own and each other's,
including codes nobody ever minted. After every step the server's answer is
compared with a reference model of what the rules in CLAUDE.md say must
happen: the status code, whose turn it is, where each piece stands, what
the result says, what `/mine` returns. The model also knows every secret
and Joker task dealt, and fails the run if one reaches the wrong phone.

Tribute plays too. Anyone may buy access or be refunded at any point, a
delivery may be late (older than what the server last applied, which then
changes nothing) and any of them may be delivered again with a new
`sent_at` (which is the same event). Whether a person has paid is state in
the model, not a constant, so everything that depends on it - the size of a
room they open, whether they may start a test or a board - follows the
money; what is already open stays as it was opened.

When a check fails, Hypothesis shrinks the run to the shortest sequence of
steps that still fails and prints it — that is the bug report.

The dice are Hypothesis's too: the server still throws them, but through
`steps69.roll_dice`, which the machine patches to the value it drew, so a
failing game replays exactly and shrinks like everything else.

Budget: E2E_FUZZ_EXAMPLES runs (default 8, a few seconds) of up to
E2E_FUZZ_STEPS steps (default 30). CI's pull-request job raises both, and the
nightly job runs 400 x 100: about thirteen minutes, and deep enough to reach
every finale, completed test and superseded retake many times over.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck
from hypothesis import event as _hypothesis_event
from hypothesis import settings as hsettings
from hypothesis import strategies as st
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    initialize,
    invariant,
    multiple,
    precondition,
    rule,
    run_state_machine_as_test,
)

from vechnost_bot import invites, steps69
from vechnost_bot.compat import TOTAL_QUESTIONS, build_result
from vechnost_bot.freemium import FREE_CARDS_PER_DECK
from vechnost_bot.payments import throttle

from .harness import LeakDetected, Player, Server

pytestmark = [pytest.mark.fuzz, pytest.mark.inprocess_only]

EXAMPLES = int(os.environ.get("E2E_FUZZ_EXAMPLES", "8"))
STEPS = int(os.environ.get("E2E_FUZZ_STEPS", "30"))

ACTORS = st.sampled_from(["alice", "bob", "carol"])
PAID = {"alice": True, "bob": False, "carol": True}  # at the start of a run
DECKS = {
    ("Acquaintance", 1, "questions"): 30,
    ("For Couples", 2, "questions"): 30,
    ("Sex", None, "tasks"): 14,
    ("Provocation", None, "questions"): 34,
}
PIECES = ("hearts", "spades", "clubs", "diamonds")
BOARD = steps69.BOARD_SIZE
SECRETS = {c.id: c.secret for c in steps69.load_cells() if c.kind == "secret"}
JOKERS = {t.id: t.text for tasks in steps69.load_jokers().values() for t in tasks}
FINALES = [c.id for c in steps69.load_finale().choices]
GHOST = st.builds(invites.new_code)

# How deep the runs went: a machine that never reaches a finale or completes
# a test is only exercising the front door. Written to E2E_REPORT_DIR (the
# CI artifact) and printed with -s.
REACHED: Counter[str] = Counter()


def event(name: str) -> None:
    _hypothesis_event(name)
    REACHED[name] += 1


@dataclass
class RoomModel:
    creator: str
    total: int
    full: int
    adult: bool = False
    guest: str | None = None
    idx: int = 0
    turn: int = 0
    finished: bool = False

    def seats(self) -> tuple[str, str | None]:
        return self.creator, self.guest

    def open_if_paid(self, paid: dict[str, bool]) -> None:
        """A room holding the free preview gets the rest of its deck the
        moment either player has access. A room that had finished on its
        last free card carries on from the next one; the turn stays where
        the finishing tap passed it. Whatever a player sends, this happens
        first (the server may do it at the next request that succeeds; no
        one can tell the difference)."""
        if self.total < self.full and any(paid[p] for p in self.seats() if p):
            self.total = self.full
            if self.finished:
                self.finished = False
                self.idx += 1
            event("room: a payment opened the rest of the deck")


@dataclass
class CompatModel:
    creator: str
    created: int = 0  # creation order: a completed test supersedes older ones only
    guest: str | None = None
    answers: dict[str, list[int | None]] = field(default_factory=lambda: {
        "creator": [None] * TOTAL_QUESTIONS, "guest": [None] * TOTAL_QUESTIONS,
    })
    finished: int | None = None  # completion order, for /mine

    def seats(self) -> tuple[str, str | None]:
        return self.creator, self.guest

    def complete(self) -> bool:
        return all(
            value is not None for side in self.answers.values() for value in side
        )


@dataclass
class GameModel:
    creator: str
    mode: str
    pieces: list[str | None]
    touched: int
    guest: str | None = None
    positions: list[int] = field(default_factory=lambda: [1, 1])
    rolls: list[int] = field(default_factory=lambda: [0, 0])
    turn: int = 0
    finished: bool = False
    finale: str | None = None
    jokers: list[str | None] = field(default_factory=lambda: [None, None])

    def seats(self) -> tuple[str, str | None]:
        return self.creator, self.guest

    def home(self, seat: int) -> bool:
        return self.positions[seat] >= BOARD


class TwoUsers(RuleBasedStateMachine):
    """The machine. `SERVER` is set per test run, before Hypothesis starts."""

    SERVER: Server

    rooms = Bundle("rooms")
    tests = Bundle("tests")
    games = Bundle("games")

    def __init__(self) -> None:
        super().__init__()
        server = self.SERVER
        server.transcript.exchanges.clear()
        self.people: dict[str, Player] = {
            name: server.player(name.capitalize(), paid=PAID[name]) for name in PAID
        }
        self.room_models: dict[str, RoomModel] = {}
        self.test_models: dict[str, CompatModel] = {}
        self.game_models: dict[str, GameModel] = {}
        self.clock = 0
        self.completions = 0
        self.last: dict[str, str] = {}
        # The money. `decided` is when the last event applied to a person's
        # access happened; the purchases above happened just before
        # `started`, and a person nobody has paid for has none on file.
        self.started = datetime.now(UTC)
        # Who has access now: Bob may buy it in the middle of a run.
        self.paid = dict(PAID)
        self.decided: dict[str, datetime | None] = {
            name: self.started if PAID[name] else None for name in PAID
        }
        self.sent: dict[str, list[bytes]] = {name: [] for name in PAID}

    # -- plumbing -----------------------------------------------------------

    def call(
        self, actor: str, method: str, path: str, body: Any = None, *, expect: int
    ) -> Any:
        """One request by one person; the status must be what the model says."""
        throttle.reset()  # budgets are the throttle suite's business, not this one's
        response = self.people[actor].call(method, path, json_body=body)
        assert response.status_code == expect, (
            f"{actor}: {method} {path} -> {response.status_code}, "
            f"the rules say {expect}: {response.text[:300]}"
        )
        return response.json() if response.status_code == 200 else None

    def tick(self) -> int:
        self.clock += 1
        return self.clock

    @staticmethod
    def seat_of(model: Any, actor: str) -> int | None:
        creator, guest = model.seats()
        if actor == creator:
            return 0
        if actor == guest:
            return 1
        return None

    # -- where every run starts: a couple already sitting at all three ----
    #
    # Without these a run spends its steps finding two people and one code
    # by chance, and the deep states - a finale, a completed test, a retake -
    # are almost never reached. Random creates, joins and strangers still
    # happen on top.

    @initialize(target=rooms)
    def a_couple_opens_a_room(self) -> Any:
        code = self.create_room("alice", ("Acquaintance", 1, "questions"))
        self.join_room("bob", code)
        return code

    @initialize(target=tests)
    def a_couple_starts_the_test(self) -> Any:
        code = self.create_test("alice")
        self.join_test("bob", code)
        return code

    @initialize(target=games)
    def a_couple_opens_a_board(self) -> Any:
        code = self.create_game("alice", "duo", "hearts")
        self.join_game("bob", code, None)
        return code

    @rule(actor=ACTORS, code=GHOST)
    def probe_a_code_nobody_minted(self, actor: str, code: str) -> None:
        """Every door answers a code that was never minted with the same 404."""
        for method, path, body in (
            ("POST", f"/api/rooms/{code}/join", None),
            ("GET", f"/api/rooms/{code}", None),
            ("POST", f"/api/rooms/{code}/advance", None),
            ("POST", f"/api/compat/{code}/join", None),
            ("GET", f"/api/compat/{code}", None),
            ("POST", f"/api/compat/{code}/answer", {"index": 0, "value": 1}),
            ("GET", f"/api/compat/{code}/result", None),
            ("DELETE", f"/api/compat/{code}", None),
            ("POST", f"/api/steps69/{code}/join", {}),
            ("GET", f"/api/steps69/{code}", None),
            ("GET", f"/api/steps69/{code}/board", None),
            ("POST", f"/api/steps69/{code}/roll", None),
            ("POST", f"/api/steps69/{code}/finale", {"choice": FINALES[0]}),
            ("DELETE", f"/api/steps69/{code}", None),
        ):
            self.call(actor, method, path, body, expect=404)

    # -- rooms --------------------------------------------------------------

    @rule(target=rooms, actor=ACTORS, deck=st.sampled_from(sorted(DECKS, key=str)))
    def create_room(self, actor: str, deck: tuple[str, int | None, str]) -> Any:
        theme, level, kind = deck
        state = self.call(actor, "POST", "/api/rooms?lang=ru",
                          {"theme": theme, "level": level, "type": kind}, expect=200)
        size = DECKS[deck]
        total = size if self.paid[actor] else min(FREE_CARDS_PER_DECK, size)
        model = RoomModel(creator=actor, total=total, full=size, adult=theme == "Sex")
        self.room_models[state["code"]] = model
        self.check_room(state, model, actor)
        self.last["room"] = state["code"]
        return state["code"]

    @rule(actor=ACTORS, code=rooms, adult=st.booleans())
    def join_room(self, actor: str, code: str, adult: bool = True) -> None:
        """`adult` is the app's 18+ answer, sent as `nsfw=1`: the seat at an
        18+ deck waits for it, and nothing else asks."""
        model = self.room_models.get(code)
        path = f"/api/rooms/{code}/join" + ("?nsfw=1" if adult else "")
        if model is None:
            self.call(actor, "POST", path, expect=404)
            return
        if actor != model.creator and model.guest is None:
            if model.adult and not adult:
                self.call(actor, "POST", path, expect=403)
                event("room: an 18+ seat waited for a yes")
                return
            model.guest = actor
        expect = 200 if actor in model.seats() else 409
        if expect == 200:
            model.open_if_paid(self.paid)
        state = self.call(actor, "POST", path, expect=expect)
        if state:
            self.check_room(state, model, actor)
        self.last["room"] = code

    @precondition(lambda self: not self.paid["bob"] and any(
        m.total < m.full and "bob" in m.seats() for m in self.room_models.values()
    ))
    @rule()
    def bob_buys_access(self) -> None:
        """The one who had not paid, paying in the middle of a game: every
        room he sits in holds the whole deck from the next request on, for
        both players, and what he creates from now on is paid.

        On the model's clock, like every other delivery here: dated by the
        wall clock, the purchase could land "before" a refund the model had
        already dated a few ticks ahead, and the server - rightly - ignored
        it as stale."""
        happened = self.moment(late=False)
        body = self.SERVER.webhook_body("new_digital_product", self.people["bob"], created_at=happened)
        self.sent["bob"].append(body)
        answer = self.deliver(body)
        assert answer["action"] == "grant", answer
        self.paid["bob"] = True
        self.decided["bob"] = happened
        event("bob bought access in the middle of a game")

    @rule(actor=ACTORS, code=rooms)
    def poll_room(self, actor: str, code: str) -> None:
        model = self.room_models.get(code)
        if model is None or actor not in model.seats():
            self.call(actor, "GET", f"/api/rooms/{code}", expect=404)
            return
        model.open_if_paid(self.paid)
        self.check_room(self.call(actor, "GET", f"/api/rooms/{code}", expect=200), model, actor)

    @rule(actor=ACTORS, code=rooms)
    def advance_room(self, actor: str, code: str) -> None:
        self.advance(actor, code)

    @rule(code=rooms, turns=st.integers(1, 40))
    def play_a_while_in_a_room(self, code: str, turns: int) -> None:
        """The couple actually playing: the turn holder turns the card."""
        model = self.room_models.get(code)
        for _ in range(turns):
            if model is None or model.guest is None or model.finished:
                return
            self.advance(model.seats()[model.turn] or "", code)

    def advance(self, actor: str, code: str) -> None:
        model = self.room_models.get(code)
        path = f"/api/rooms/{code}/advance"
        if model is None or actor not in model.seats():
            self.call(actor, "POST", path, expect=404)
            return
        model.open_if_paid(self.paid)
        if model.guest is None or model.finished:
            self.call(actor, "POST", path, expect=409)
            return
        if model.seats()[model.turn] != actor:
            self.call(actor, "POST", path, expect=403)
            return
        if model.idx + 1 >= model.total:
            model.finished = True
            event("room: a deck played to the end")
        else:
            model.idx += 1
        model.turn = 1 - model.turn
        self.check_room(self.call(actor, "POST", path, expect=200), model, actor)
        self.last["room"] = code

    def check_room(self, state: dict[str, Any], model: RoomModel, actor: str) -> None:
        seat = self.seat_of(model, actor)
        assert state["your_role"] == ("creator" if seat == 0 else "guest")
        assert state["total"] == model.total
        assert state["full_total"] == model.full
        assert state["trimmed"] == (model.total < model.full)
        assert state["nsfw"] == model.adult
        assert state["idx"] == model.idx
        assert state["finished"] == model.finished
        assert state["started"] == (model.guest is not None)
        assert state["your_turn"] == (
            not model.finished and model.guest is not None and model.turn == seat
        )
        assert state["card_text"], "a room always shows a card"

    # -- the compatibility test --------------------------------------------

    @rule(target=tests, actor=ACTORS)
    def create_test(self, actor: str) -> Any:
        if not self.paid[actor]:
            self.call(actor, "POST", "/api/compat", expect=402)
            return multiple()
        state = self.call(actor, "POST", "/api/compat", expect=200)
        model = CompatModel(creator=actor, created=self.tick())
        self.test_models[state["code"]] = model
        self.check_test(state, model, actor)
        self.last["test"] = state["code"]
        return state["code"]

    @rule(actor=ACTORS, code=tests)
    def join_test(self, actor: str, code: str) -> None:
        model = self.test_models.get(code)
        if model is None:
            self.call(actor, "POST", f"/api/compat/{code}/join", expect=404)
            return
        if actor != model.creator and model.guest is None:
            model.guest = actor
        expect = 200 if actor in model.seats() else 409
        state = self.call(actor, "POST", f"/api/compat/{code}/join", expect=expect)
        if state:
            self.check_test(state, model, actor)
        self.last["test"] = code

    @rule(actor=ACTORS, code=tests,
          index=st.integers(0, TOTAL_QUESTIONS - 1), value=st.integers(1, 5))
    def answer(self, actor: str, code: str, index: int, value: int) -> None:
        self.give_answer(actor, code, index, value)

    @rule(code=tests, count=st.integers(1, TOTAL_QUESTIONS),
          values=st.lists(st.integers(1, 5), min_size=1, max_size=8))
    def both_answer_a_stretch(self, code: str, count: int, values: list[int]) -> None:
        """Both partners answering in earnest, from their first gap."""
        model = self.test_models.get(code)
        if model is None or model.guest is None:
            return
        for role, person in (("creator", model.creator), ("guest", model.guest)):
            gaps = [i for i, v in enumerate(model.answers[role]) if v is None][:count]
            for n, index in enumerate(gaps):
                if code not in self.test_models or self.test_models[code].finished:
                    return
                self.give_answer(person, code, index, values[n % len(values)])

    def give_answer(self, actor: str, code: str, index: int, value: int) -> None:
        model = self.test_models.get(code)
        path = f"/api/compat/{code}/answer"
        body = {"index": index, "value": value}
        if model is None or actor not in model.seats():
            self.call(actor, "POST", path, body, expect=404)
            return
        if model.guest is None or model.finished is not None:
            self.call(actor, "POST", path, body, expect=409)
            return
        role = "creator" if actor == model.creator else "guest"
        model.answers[role][index] = value
        if model.complete():
            self.completions += 1
            model.finished = self.completions
            event("compat: a test completed by both")
            # A completed test supersedes the pair's *older* tests outright;
            # a newer one still being answered is left alone.
            pair = {model.creator, model.guest}
            for other_code, other in list(self.test_models.items()):
                if (other is not model and other.guest and other.created < model.created
                        and {other.creator, other.guest} == pair):
                    del self.test_models[other_code]
                    event("compat: a retake superseded another test")
        self.check_test(self.call(actor, "POST", path, body, expect=200), model, actor)
        self.last["test"] = code

    @rule(actor=ACTORS, code=tests)
    def poll_test(self, actor: str, code: str) -> None:
        model = self.test_models.get(code)
        if model is None or actor not in model.seats():
            self.call(actor, "GET", f"/api/compat/{code}", expect=404)
            return
        self.check_test(self.call(actor, "GET", f"/api/compat/{code}", expect=200), model, actor)

    @rule(actor=ACTORS, code=tests)
    def read_result(self, actor: str, code: str) -> None:
        model = self.test_models.get(code)
        path = f"/api/compat/{code}/result"
        if model is None or actor not in model.seats():
            self.call(actor, "GET", path, expect=404)
            return
        if model.finished is None:
            self.call(actor, "GET", path, expect=409)
            return
        result = self.call(actor, "GET", path, expect=200)
        assert result == self.expected_result(model)

    @rule(actor=ACTORS)
    def my_last_result(self, actor: str) -> None:
        mine = [
            (model.finished, code, model) for code, model in self.test_models.items()
            if model.finished is not None and actor in model.seats()
        ]
        if not mine:
            self.call(actor, "GET", "/api/compat/mine", expect=404)
            return
        _, code, model = max(mine, key=lambda entry: entry[0])
        body = self.call(actor, "GET", "/api/compat/mine", expect=200)
        assert body["code"] == code
        assert body["result"] == self.expected_result(model)

    @rule(actor=ACTORS, code=tests)
    def delete_test(self, actor: str, code: str) -> None:
        model = self.test_models.get(code)
        if model is None or actor not in model.seats():
            self.call(actor, "DELETE", f"/api/compat/{code}", expect=404)
            return
        assert self.call(actor, "DELETE", f"/api/compat/{code}", expect=200) == {"deleted": True}
        del self.test_models[code]

    @staticmethod
    def expected_result(model: CompatModel) -> Any:
        creator = [int(v or 0) for v in model.answers["creator"]]
        guest = [int(v or 0) for v in model.answers["guest"]]
        return json.loads(build_result(creator, guest).model_dump_json())

    def check_test(self, state: dict[str, Any], model: CompatModel, actor: str) -> None:
        role = "creator" if actor == model.creator else "guest"
        other = "guest" if role == "creator" else "creator"
        assert state["your_role"] == role
        assert state["started"] == (model.guest is not None)
        assert state["answered"] == sum(v is not None for v in model.answers[role])
        assert state["partner_answered"] == sum(v is not None for v in model.answers[other])
        assert state["answered_indices"] == [
            i for i, v in enumerate(model.answers[role]) if v is not None
        ]
        assert state["finished"] == (model.finished is not None)
        assert not {"creator_answers", "guest_answers", "answers"} & set(state)

    # -- «69 ступеней» -------------------------------------------------------

    @rule(target=games, actor=ACTORS, mode=st.sampled_from(["duo", "duo", "solo"]),
          piece=st.sampled_from([*PIECES, "unicorn"]))
    def create_game(self, actor: str, mode: str, piece: str) -> Any:
        body = {"mode": mode, "piece": piece}
        if not self.paid[actor]:
            self.call(actor, "POST", "/api/steps69", body, expect=402)
            return multiple()
        if piece not in PIECES:
            self.call(actor, "POST", "/api/steps69", body, expect=400)
            return multiple()
        state = self.call(actor, "POST", "/api/steps69?lang=ru", body, expect=200)
        second = next(p for p in PIECES if p != piece) if mode == "solo" else None
        model = GameModel(creator=actor, mode=mode, pieces=[piece, second], touched=self.tick())
        self.game_models[state["code"]] = model
        self.check_game(state, model, actor)
        self.last["game"] = state["code"]
        return state["code"]

    @rule(actor=ACTORS, code=games, piece=st.none() | st.sampled_from([*PIECES, "unicorn"]))
    def join_game(self, actor: str, code: str, piece: str | None) -> None:
        model = self.game_models.get(code)
        path = f"/api/steps69/{code}/join?lang=ru"
        if model is None:
            self.call(actor, "POST", path, {"piece": piece}, expect=404)
            return
        if model.mode == "solo":
            self.call(actor, "POST", path, {"piece": piece}, expect=409)
            return
        if actor != model.creator and model.guest is None:
            model.guest = actor
            taken = model.pieces[0]
            model.pieces[1] = (
                piece if piece in PIECES and piece != taken
                else next(p for p in PIECES if p != taken)
            )
            model.touched = self.tick()
        expect = 200 if actor in model.seats() else 409
        state = self.call(actor, "POST", path, {"piece": piece}, expect=expect)
        if state:
            self.check_game(state, model, actor)
        self.last["game"] = code

    @rule(actor=ACTORS, code=games, die=st.integers(1, 6))
    def roll(self, actor: str, code: str, die: int) -> None:
        self.throw(actor, code, die)

    @rule(code=games, dice=st.lists(st.integers(1, 6), min_size=1, max_size=60))
    def play_a_while_on_the_board(self, code: str, dice: list[int]) -> None:
        """The couple playing in earnest: whoever is on turn rolls."""
        for die in dice:
            model = self.game_models.get(code)
            if model is None or model.finished or (model.mode == "duo" and model.guest is None):
                return
            if model.home(model.turn):
                return
            mover = model.creator if model.mode == "solo" else model.seats()[model.turn]
            self.throw(mover or "", code, die)

    def throw(self, actor: str, code: str, die: int) -> None:
        model = self.game_models.get(code)
        path = f"/api/steps69/{code}/roll?lang=ru"
        if model is None or actor not in model.seats():
            self.call(actor, "POST", path, expect=404)
            return
        if model.finished:
            self.call(actor, "POST", path, expect=409)
            return
        if model.mode == "solo":
            mover = model.turn
        else:
            if model.guest is None:
                self.call(actor, "POST", path, expect=409)
                return
            mover = self.seat_of(model, actor) or 0
        if model.home(mover):
            self.call(actor, "POST", path, expect=409)
            return
        if model.mode == "duo" and model.turn != mover:
            self.call(actor, "POST", path, expect=403)
            return

        move = steps69.resolve_move(model.positions[mover], die)
        with patch.object(steps69, "roll_dice", return_value=die):
            state = self.call(actor, "POST", path, expect=200)
        model.positions[mover] = move.position
        model.rolls[mover] += 1
        other = 1 - mover
        model.turn = other if not model.home(other) else mover
        model.touched = self.tick()
        if model.home(0) and model.home(1):
            event(f"steps69: both pieces home ({model.mode})")
        if move.position in SECRETS:
            event("steps69: a secret dealt")
        last = state["last"]
        assert (last["seat"], last["from"], last["roll"], last["landed"], last["to"]) == (
            mover, move.start, die, move.landed, move.position
        )
        assert last["event"] == move.event
        mover_cell = state["you"]["cell"] if state["you"]["seat"] == mover else None
        if mover_cell is not None and mover_cell["kind"] == "joker":
            dealt = mover_cell["joker"]
            assert dealt, "a Joker square deals a task"
            model.jokers[mover] = dealt["text"]
            event("steps69: a Joker dealt")
        else:
            model.jokers[mover] = None
        self.check_game(state, model, actor)
        self.last["game"] = code

    @rule(actor=ACTORS, code=games, choice=st.sampled_from([*FINALES, "elope"]))
    def choose_finale(self, actor: str, code: str, choice: str) -> None:
        model = self.game_models.get(code)
        path = f"/api/steps69/{code}/finale?lang=ru"
        body = {"choice": choice}
        if model is None or actor not in model.seats():
            self.call(actor, "POST", path, body, expect=404)
            return
        if not (model.home(0) and model.home(1)):
            self.call(actor, "POST", path, body, expect=409)
            return
        if choice not in FINALES:
            # Not 404: that reads as "game deleted" on the phone.
            self.call(actor, "POST", path, body, expect=422)
            return
        if model.finished and model.finale != choice:
            self.call(actor, "POST", path, body, expect=409)
            return
        model.finished, model.finale = True, choice
        event(f"steps69: finale chosen ({model.mode})")
        self.check_game(self.call(actor, "POST", path, body, expect=200), model, actor)

    @rule(actor=ACTORS, code=games)
    def poll_game(self, actor: str, code: str) -> None:
        model = self.game_models.get(code)
        if model is None or actor not in model.seats():
            self.call(actor, "GET", f"/api/steps69/{code}", expect=404)
            return
        self.check_game(self.call(actor, "GET", f"/api/steps69/{code}?lang=ru", expect=200), model, actor)

    @rule(actor=ACTORS, code=games)
    def look_at_the_board(self, actor: str, code: str) -> None:
        model = self.game_models.get(code)
        if model is None or actor not in model.seats():
            self.call(actor, "GET", f"/api/steps69/{code}/board", expect=404)
            return
        text = json.dumps(self.call(actor, "GET", f"/api/steps69/{code}/board", expect=200),
                          ensure_ascii=False)
        for secret in SECRETS.values():
            if secret in text:
                raise LeakDetected("a secret is printed on the board")
        for task in JOKERS.values():
            if task in text:
                raise LeakDetected("a Joker task is printed on the board")

    @rule(actor=ACTORS)
    def resume_my_game(self, actor: str) -> None:
        mine = [
            (model.touched, code) for code, model in self.game_models.items()
            if not model.finished and actor in model.seats()
        ]
        if not mine:
            self.call(actor, "GET", "/api/steps69/mine", expect=404)
            return
        _, code = max(mine)
        assert self.call(actor, "GET", "/api/steps69/mine", expect=200)["code"] == code

    @rule(actor=ACTORS, code=games)
    def delete_game(self, actor: str, code: str) -> None:
        model = self.game_models.get(code)
        if model is None or actor not in model.seats():
            self.call(actor, "DELETE", f"/api/steps69/{code}", expect=404)
            return
        assert self.call(actor, "DELETE", f"/api/steps69/{code}", expect=200) == {"deleted": True}
        del self.game_models[code]

    def check_game(self, state: dict[str, Any], model: GameModel, actor: str) -> None:
        seat = self.seat_of(model, actor)
        solo = model.mode == "solo"
        assert state["your_seat"] == seat
        assert state["started"] == (solo or model.guest is not None)
        assert state["turn"] == model.turn
        assert state["finished"] == model.finished
        assert state["finale_choice"] == model.finale
        assert state["both_home"] == (model.home(0) and model.home(1))
        views = {state["you"]["seat"]: state["you"], state["partner"]["seat"]: state["partner"]}
        assert set(views) == {0, 1}
        for s in (0, 1):
            assert views[s]["position"] == model.positions[s]
            assert views[s]["rolls"] == model.rolls[s]
            assert views[s]["piece"] == model.pieces[s]
        if solo:
            return
        assert state["you"]["seat"] == seat, "two phones each show their own piece"
        mine, theirs = model.positions[seat or 0], model.positions[1 - (seat or 0)]
        partner_cell = state["partner"]["cell"]
        if partner_cell.get("secret") or partner_cell.get("joker") or partner_cell.get("text"):
            raise LeakDetected(f"{actor} sees the partner's square as its mover does")
        text = json.dumps(state, ensure_ascii=False)
        if theirs != mine and theirs in SECRETS and SECRETS[theirs] in text:
            raise LeakDetected(f"{actor} received the partner's secret on {theirs}")
        their_joker = model.jokers[1 - (seat or 0)]
        if their_joker and their_joker in text and their_joker != model.jokers[seat or 0]:
            raise LeakDetected(f"{actor} received the partner's Joker task")

    # -- Tribute ------------------------------------------------------------

    def moment(self, late: bool) -> datetime:
        """When a delivered event happened. Each is later than the one
        before, so no two are one event; a late one happened a day before
        the run began - before anything the server has applied - and is
        only now getting through."""
        tick = timedelta(seconds=self.tick())
        return self.started + tick - (timedelta(days=1) if late else timedelta(0))

    def deliver(self, body: bytes) -> dict[str, Any]:
        throttle.reset()
        response = self.SERVER.deliver(body, label="fuzzer")
        assert response.status_code == 200, f"a delivery -> {response.status_code}: {response.text}"
        return response.json()

    def check_access(self, actor: str) -> None:
        """What the person's own phone is told, after Tribute's word."""
        access = self.call(actor, "GET", "/api/questions?lang=ru", expect=200)["access"]
        assert access["paid"] == self.paid[actor], (
            f"{actor}: paid={access['paid']}, the rules say {self.paid[actor]}"
        )

    @rule(actor=ACTORS, refund=st.booleans(), late=st.booleans())
    def tribute_delivers(self, actor: str, refund: bool, late: bool) -> None:
        """A purchase or its refund, as it happens - or late, a first
        attempt that failed and is only now getting through."""
        name = "digital_product_refunded" if refund else "new_digital_product"
        happened = self.moment(late)
        body = self.SERVER.webhook_body(name, self.people[actor], created_at=happened)
        self.sent[actor].append(body)
        decided = self.decided[actor]
        answer = self.deliver(body)
        if decided is not None and decided > happened:
            assert (answer["action"], answer["message"]) == ("ignore", "Stale event ignored")
            event("payments: an event older than the last one applied, ignored")
        else:
            assert answer["action"] == ("revoke" if refund else "grant"), answer
            self.paid[actor] = not refund
            self.decided[actor] = happened
            event("payments: a refund" if refund else "payments: a purchase")
        self.check_access(actor)

    @rule(actor=ACTORS, which=st.integers(0, 1000))
    def tribute_delivers_again(self, actor: str, which: int) -> None:
        """Any earlier delivery once more, with a new `sent_at`: the same
        event, so nothing changes."""
        sent = self.sent[actor]
        if not sent:
            return
        answer = self.deliver(self.SERVER.redelivery(sent[which % len(sent)]))
        assert "already processed" in answer["message"], answer
        event("payments: a redelivery recognised")
        self.check_access(actor)

    # -- both phones, after every step -------------------------------------

    @invariant()
    def both_phones_agree(self) -> None:
        """The last thing touched looks the same from both seats."""
        code = self.last.get("game")
        model = self.game_models.get(code or "")
        if model is not None and model.guest is not None:
            for person in model.seats():
                self.check_game(
                    self.call(person or "", "GET", f"/api/steps69/{code}?lang=ru", expect=200),
                    model, person or "",
                )
        code = self.last.get("room")
        room = self.room_models.get(code or "")
        if room is not None and room.guest is not None:
            texts = {
                self.call(p or "", "GET", f"/api/rooms/{code}", expect=200)["card_text"]
                for p in room.seats()
            }
            assert len(texts) == 1, "both phones show the same card"


def test_three_people_doing_anything(server: Server) -> None:
    TwoUsers.SERVER = server
    REACHED.clear()
    run_state_machine_as_test(
        TwoUsers,
        settings=hsettings(
            max_examples=EXAMPLES,
            stateful_step_count=STEPS,
            deadline=None,
            database=None,
            print_blob=True,
            suppress_health_check=[
                HealthCheck.too_slow,
                HealthCheck.filter_too_much,
                HealthCheck.data_too_large,
            ],
        ),
    )
    summary = {"examples": EXAMPLES, "steps": STEPS, "reached": dict(sorted(REACHED.items()))}
    print("\nfuzz coverage:", json.dumps(summary, ensure_ascii=False, indent=2))
    report_dir = os.environ.get("E2E_REPORT_DIR")
    if report_dir:
        Path(report_dir).mkdir(parents=True, exist_ok=True)
        (Path(report_dir) / "fuzz_coverage.json").write_text(json.dumps(summary, indent=2))
