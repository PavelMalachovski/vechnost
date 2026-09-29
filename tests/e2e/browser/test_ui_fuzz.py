"""Two phones, a random evening: the Mini App's UI fuzzer.

The API fuzzer (test_duo_fuzz.py) proves the server keeps its rules whatever
two people send it. This one proves the app keeps its head whatever two
people *do*: from a room, a test or a board the two already share, both
phones take turns at something a person can do - tap any visible, enabled
control, swipe a card, scroll whatever scrolls, press Telegram's Back
button, wait, close the app and open it again, open the invite again - for
a number of steps. Taps, swipes and scrolls are real input (touch.py). The
dice, «next» and the answers are tapped more often than the rest, a phone
at the table mostly plays, and one that wandered off comes back through the
invite more often, so an evening moves its game forward instead of circling
the home screen. After every
step, on both phones:

* no uncaught page error and no console error beyond the benign ones;
* no failed `/api` call, except the 4xx the app is built to expect
  (`EXPECTED`, each with the reason) - and no 5xx at all;
* no horizontal overflow: nothing on the screen or an open overlay reaches
  past the edges of the phone;
* Back closed the top layer: the overlay on top if there was one, else the
  screen;
* the full-screen loader never stays up for more than 10 s, and every open
  overlay has a button out of it;
* when both phones show the same room, board or test and their polls have
  settled, each shows what the server holds for its own player: the same
  card and progress, the pieces on the same squares, one "your turn"
  between them, the partner's progress.

And at the end both phones find their way back to the home screen.

A run is seeded. A failure prints the seed, the replay command and every
action both phones took; E2E_UI_FUZZ_SEED=<seed> replays the same choices
(timing, polls and the server's dice can still differ). Budget: every arena
runs E2E_UI_FUZZ_RUNS times for E2E_UI_FUZZ_STEPS steps - short on a pull
request, longer at night (.github/workflows/e2e.yml).
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pytest

from ..harness import Player, Server, code_from_invite
from .app import PROGRESS_JS, s69_your_turn, wait_home
from .phones import REPORT_DIR, ApiCall, Device, Phone

pytestmark = [pytest.mark.browser, pytest.mark.ui_fuzz]

RUNS = int(os.environ.get("E2E_UI_FUZZ_RUNS", "1"))
STEPS = int(os.environ.get("E2E_UI_FUZZ_STEPS", "25"))
PINNED_SEED = os.environ.get("E2E_UI_FUZZ_SEED", "")
BASE_SEED = int(PINNED_SEED) if PINNED_SEED else random.SystemRandom().randrange(1, 1_000_000)
ARENAS = ("room", "s69", "compat")
LOADER_LIMIT_MS = 10_000
# The server allows ten joins in five minutes per person (throttle.py), and
# every opening of an invite is a join: one every half minute stays inside it.
INVITE_EVERY_S = 30.0
SETTLE_S = 9.0  # three or four polls
POLL = 15_000
# A state poll: GET /api/<feature>/<CODE>, which only a participant sends.
STATE_POLL = re.compile(r"^/api/(rooms|steps69|compat)/([A-Z2-9]{6,16})(?:\?|$)")
CODE = r"[A-Z2-9]{6,16}"

# The 4xx the app asks for knowing it may hear them, and handles: anything
# else is a failure. (method, path, statuses, why)
EXPECTED: list[tuple[str, re.Pattern[str], frozenset[int], str]] = [
    (m, re.compile(p), frozenset(s), why)
    for m, p, s, why in [
        ("POST", r"^/api/(steps69|compat)(\?|$)", {402}, "an unpaid partner starts a paid feature"),
        ("POST", rf"^/api/rooms/{CODE}/join\b", {403}, "an 18+ room, before the age answer"),
        (
            "POST",
            rf"^/api/(rooms|compat|steps69)/{CODE}/join\b",
            {404, 409, 410},
            "the invite is stale: the seat is taken, or the partner deleted it",
        ),
        (
            "POST",
            rf"^/api/rooms/{CODE}/advance\b",
            {403, 409},
            "a tap that crossed the partner's turn or the deck's end",
        ),
        (
            "POST",
            rf"^/api/steps69/{CODE}/roll\b",
            {403, 409},
            "a roll that crossed the partner's turn or the finish",
        ),
        ("POST", rf"^/api/steps69/{CODE}/finale\b", {409}, "the partner chose the finale first"),
        ("POST", rf"^/api/compat/{CODE}/answer\b", {409}, "an answer after the test was complete"),
        (
            "GET",
            rf"^/api/(rooms|compat|steps69)/{CODE}(/board|/result)?(\?|$)",
            {404, 410},
            "the partner deleted it",
        ),
        (
            "DELETE",
            rf"^/api/(compat|steps69)/{CODE}(\?|$)",
            {404, 410},
            "already deleted by the partner",
        ),
        ("GET", r"^/api/card\?", {403}, "an unpaid partner shares a card outside a room"),
    ]
]

# What a finger can tap in the top layer: every control, a board square, a
# question number in the compatibility result, a veiled secret.
CANDIDATES = """() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden'
        && cs.display !== 'none' && cs.pointerEvents !== 'none';
  };
  const overlays = [...document.querySelectorAll('.overlay.show')];
  const overlay = overlays[overlays.length - 1] || null;
  const screen = document.querySelector('.screen.active');
  const scope = overlay || screen;
  const tappable = scope ? [...scope.querySelectorAll(
      'button, summary, [role=button], .s69-spoiler')]
    .filter(el => !el.disabled && visible(el) && !el.closest('.card.under')) : [];
  const scrollers = scope ? [scope, ...scope.querySelectorAll('*')].filter(el => {
      const cs = getComputedStyle(el);
      return /(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 4
          && visible(el);
    }) : [];
  window.__fuzzTargets = tappable;
  window.__fuzzScrollers = scrollers;
  // How often each is tapped: what moves a game on (the dice, «next», an
  // answer, a finale) far more than the rest. The board's squares are a
  // picture and take no tap.
  const forward = '#s69Dice, #btnNext, #libNext, .compat-opt, #s69FinaleChoices button';
  const weight = (el) => el.matches(forward) ? 8 : 1;
  const label = (el) => el.id ? '#' + el.id
    : el.dataset.module ? 'module ' + el.dataset.module
    : el.dataset.value ? 'answer ' + el.dataset.value
    : (el.className || el.tagName).toString().split(' ')[0];
  return {
    screen: screen ? screen.id : null,
    overlay: overlay ? overlay.id : null,
    overlayExits: overlay ? tappable.filter(el => el.tagName === 'BUTTON').length : null,
    targets: tappable.map(el => label(el) + ' ' +
                          JSON.stringify((el.innerText || '').trim().slice(0, 24))),
    weights: tappable.map(weight),
    scrollers: scrollers.map(el => el.id ? '#' + el.id : String(el.className).split(' ')[0]),
    card: !!(scope && scope.querySelector('.card.top')),
    loader: document.getElementById('loader').classList.contains('show'),
  };
}"""

# Where to put the finger: the middle of a control, brought into reach; for
# a scroll, a point of the scroller that is not a control, because on WebKit
# a scroll starts with a press (touch.py) and a press on a button is a tap.
AIM = """([kind, i]) => {
  const el = ((kind === 'scroll' ? window.__fuzzScrollers : window.__fuzzTargets) || [])[i];
  if (!el || !el.isConnected) return null;
  if (kind !== 'scroll') el.scrollIntoView({block: 'center', inline: 'center'});
  const r = el.getBoundingClientRect();
  const top = Math.max(r.top, 0), bottom = Math.min(r.bottom, innerHeight);
  const left = Math.max(r.left, 0), right = Math.min(r.right, innerWidth);
  if (right <= left || bottom <= top) return null;
  if (kind !== 'scroll') return [(left + right) / 2, (top + bottom) / 2, bottom - top];
  const controls = 'button, a, summary, input, select, textarea, [role=button]';
  for (const fy of [0.5, 0.3, 0.7, 0.15, 0.85]) {
    for (const fx of [0.5, 0.15, 0.85]) {
      const x = left + (right - left) * fx, y = top + (bottom - top) * fy;
      const hit = document.elementFromPoint(x, y);
      if (hit && el.contains(hit) && !hit.closest(controls)) return [x, y, bottom - top];
    }
  }
  return null;
}"""

CARD_BOX = """() => {
  const card = document.querySelector('.screen.active .card.top');
  if (!card) return null;
  const r = card.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2, r.width, r.height];
}"""

# Anything on the screen or an open overlay that reaches past the phone's
# edges. Cards are left out: they fly off the side on purpose.
OVERFLOW = """() => {
  const W = document.documentElement.clientWidth;
  const roots = [document.querySelector('.screen.active'),
                 ...document.querySelectorAll('.overlay.show')].filter(Boolean);
  const found = [];
  for (const root of roots) {
    for (const el of [root, ...root.querySelectorAll('*')]) {
      if (el.closest('.card') || el.classList.contains('confetti')) continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (r.right <= W + 1 && r.left >= -1) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      let scroller = false;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        if (/(auto|scroll)/.test(getComputedStyle(p).overflowX)) { scroller = true; break; }
      }
      if (scroller) continue;
      const name = el.id ? '#' + el.id : el.tagName.toLowerCase() +
        (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '');
      found.push(name + ' ' + Math.round(r.left) + '..' + Math.round(r.right) + ' of ' + W);
    }
  }
  const page = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth);
  if (page > W + 1) found.unshift('the page is ' + page + ' wide on a ' + W + ' screen');
  return found.slice(0, 6);
}"""

TOP_LAYER = """() => {
  const overlays = [...document.querySelectorAll('.overlay.show')];
  const screen = document.querySelector('.screen.active');
  return {overlay: overlays.length ? overlays[overlays.length - 1].id : null,
          screen: screen ? screen.id : null};
}"""


# The screen each arena is played on.
ARENA_SCREENS = {"room": {"deck"}, "s69": {"s69Board"}, "compat": {"compatQuiz", "compatResult"}}


class FuzzFailure(AssertionError):
    pass


def expected(call: ApiCall) -> bool:
    return any(
        call.method == method and pattern.search(call.path) and call.status in statuses
        for method, pattern, statuses, _ in EXPECTED
    )


@dataclass
class UiFuzz:
    """Both phones, one random evening, checked after every step."""

    rng: random.Random
    seed: int
    arena: str
    device: Device
    phones: dict[str, Phone]
    players: dict[str, Player]
    log: list[str] = field(default_factory=list)
    games: dict[str, tuple[str, str]] = field(default_factory=dict)
    invite: str | None = None
    counts: Counter[str] = field(default_factory=Counter)
    screens: Counter[str] = field(default_factory=Counter)
    seen_api: dict[str, int] = field(default_factory=dict)
    statuses: Counter[str] = field(default_factory=Counter)
    invited_at: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, phone in self.phones.items():
            phone.page.on("request", lambda request, name=name: self._saw(name, request))
            self.seen_api[name] = 0

    def _saw(self, name: str, request: Any) -> None:
        if request.method != "GET":
            return
        path = request.url.split("://", 1)[-1]
        path = path[path.find("/") :]
        match = STATE_POLL.search(path)
        if match:
            self.games[name] = (match.group(1), match.group(2))

    # -- reporting -----------------------------------------------------------

    def say(self, line: str) -> None:
        self.log.append(f"{len(self.log) + 1:>3}. {line}")

    def fail(self, why: str) -> None:
        for phone in self.phones.values():
            try:
                phone.shot("fuzz-failure")
            except Exception:
                pass
        self.save(failed=why)
        raise FuzzFailure(
            f"UI fuzz, seed {self.seed}, {self.arena} on {self.device.label}: {why}\n"
            f"Replay: E2E_UI_FUZZ_SEED={self.seed} E2E_UI_FUZZ_STEPS={STEPS} "
            f"E2E_PHONES={self.device.name} E2E_BROWSER=1 pytest "
            f"tests/e2e/browser/test_ui_fuzz.py -n0 -k '{self.arena}'\n"
            "Actions, in order:\n" + "\n".join(self.log[-120:])
        )

    def save(self, failed: str | None = None) -> None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        name = f"ui_fuzz_{self.device.name}_{self.arena}_{self.seed}.json"
        (REPORT_DIR / name).write_text(
            json.dumps(
                {
                    "seed": self.seed,
                    "arena": self.arena,
                    "phone": self.device.name,
                    "steps": STEPS,
                    "failed": failed,
                    "actions": dict(self.counts),
                    "screens": dict(self.screens),
                    "api": dict(self.statuses),
                    "log": self.log,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- the evening ---------------------------------------------------------

    def setup(self) -> None:
        """Alice starts something through the UI; Bob opens her link."""
        alice, bob = self.phones["Alice"], self.phones["Bob"]
        wait_home(alice)
        if self.arena == "room":
            alice.tap("#btnCoop")
            alice.tap("#btnCoopCreate")
            alice.screen("themes")
            alice.page.locator("#themeList .theme-card").first.tap()
            alice.screen("levels")
            alice.page.locator("#levelList .level-card").first.tap()
            alice.screen("invite")
            self.invite = "duo_" + code_from_invite(alice.text("#inviteCode"))
            screen = "deck"
        elif self.arena == "s69":
            alice.tap("#btnS69")
            alice.page.wait_for_selector("#nsfw.show")
            alice.tap("#nsfwYes")
            alice.screen("s69")
            alice.tap("#btnS69Duo")
            alice.screen("s69Invite")
            self.invite = "s69_" + code_from_invite(alice.text("#s69Code"))
            screen = "s69Board"
        else:
            alice.tap("#btnCompat")
            alice.tap("#btnCompatCreate")
            alice.screen("compatInvite")
            self.invite = "cmp_" + code_from_invite(alice.text("#compatCode"))
            screen = "compatQuiz"
        bob.open_link(self.invite)
        if self.arena == "s69":
            bob.page.wait_for_selector("#nsfw.show")
            bob.tap("#nsfwYes")
        bob.screen(screen)
        alice.screen(screen, timeout=POLL)
        self.say(f"setup: {self.arena}; Alice created it through the UI, Bob opened {self.invite}")
        self.check("setup")

    def step(self) -> None:
        name = self.rng.choice(sorted(self.phones))
        phone = self.phones[name]
        seen = phone.page.evaluate(CANDIDATES)
        where = seen["overlay"] or seen["screen"]
        self.screens[where] += 1
        # At the table a person mostly plays; away from it, they wander, go
        # back, or come back through the link.
        home = seen["screen"] in ARENA_SCREENS[self.arena] and not seen["overlay"]
        options: list[tuple[str, float]] = [
            ("tap", 12),
            ("wait", 2 if home else 1),
            ("reopen", 0.5 if home else 1),
        ]
        if seen["card"] and not seen["overlay"]:
            options.append(("swipe", 4))
        if seen["scrollers"]:
            options.append(("scroll", 1 if home else 2))
        if phone.back_button_visible():
            options.append(("back", 1 if home else 3))
        if self.invite and time.monotonic() - self.invited_at.get(name, 0.0) > INVITE_EVERY_S:
            # The link sits in both partners' chat: the creator's opens
            # their own game, the guest's their seat.
            options.append(("invite", 0.5 if home else 5))
        if not seen["targets"]:
            options = [option for option in options if option[0] != "tap"]
        kind = self.rng.choices([o for o, _ in options], [w for _, w in options])[0]
        self.counts[kind] += 1
        layer = phone.page.evaluate(TOP_LAYER)
        if kind == "tap":
            index = self.rng.choices(range(len(seen["targets"])), seen["weights"])[0]
            aim = phone.page.evaluate(AIM, ["tap", index])
            if aim is None:
                self.say(f"{name} on {where}: {seen['targets'][index]} is out of reach, skipped")
                return
            self.say(f"{name} on {where}: tap {seen['targets'][index]}")
            phone.finger.tap(aim[0], aim[1])
        elif kind == "swipe":
            box = phone.page.evaluate(CARD_BOX)
            if box is None:
                self.say(f"{name} on {where}: no card to swipe")
                return
            x, y, width, _ = box
            direction = self.rng.choice((1, -1))
            self.say(f"{name} on {where}: swipe {'right' if direction > 0 else 'left'}")
            phone.finger.drag(
                (x - direction * width * 0.3, y), (x + direction * width * 0.45, y + 6)
            )
        elif kind == "scroll":
            index = self.rng.randrange(len(seen["scrollers"]))
            aim = phone.page.evaluate(AIM, ["scroll", index])
            if aim is None:
                self.say(f"{name} on {where}: {seen['scrollers'][index]} is out of reach, skipped")
                return
            dy = self.rng.choice((1, -1)) * max(40.0, aim[2] * 0.5)
            self.say(
                f"{name} on {where}: scroll {seen['scrollers'][index]} {'down' if dy > 0 else 'up'}"
            )
            phone.finger.scroll(aim[0], aim[1], dy)
        elif kind == "back":
            self.say(f"{name} on {where}: Telegram's Back button")
            phone.press_back()
        elif kind == "wait":
            ms = self.rng.randrange(500, 3000)
            self.say(f"{name} on {where}: waits {ms} ms")
            phone.page.wait_for_timeout(ms)
        elif kind == "reopen":
            self.say(f"{name} on {where}: closes the app and opens it again")
            phone.open_link(None)
        elif kind == "invite":
            self.say(f"{name} on {where}: opens the invite link again")
            self.invited_at[name] = time.monotonic()
            phone.open_link(self.invite)
        phone.page.wait_for_timeout(350)
        self.check(kind, name, layer)

    # -- invariants ----------------------------------------------------------

    def check(
        self, kind: str, actor: str | None = None, layer: dict[str, Any] | None = None
    ) -> None:
        for name, phone in self.phones.items():
            try:
                phone.page.wait_for_selector(
                    "#loader:not(.show)", state="attached", timeout=LOADER_LIMIT_MS
                )
            except Exception:
                self.fail(f"{name}'s loader stayed up for more than {LOADER_LIMIT_MS // 1000} s")
            if phone.errors:
                self.fail(f"{name}'s app misbehaved: " + "; ".join(phone.errors))
            self.api(name, phone, navigated=kind in ("reopen", "invite") and name == actor)
            overflow = phone.page.evaluate(OVERFLOW)
            if overflow:
                self.fail(f"{name}'s screen overflows sideways: " + "; ".join(overflow))
            seen = phone.page.evaluate(CANDIDATES)
            if seen["overlay"] and not seen["overlayExits"]:
                self.fail(f"{name} is shut in #{seen['overlay']}: no button leads out of it")
        if kind == "back" and actor and layer:
            self.closed(actor, layer)
        self.agree()

    def api(self, name: str, phone: Phone, *, navigated: bool) -> None:
        """Every /api call since the last check came back as the app expects."""
        calls = phone.api[self.seen_api[name] :]
        self.seen_api[name] = len(phone.api)
        for call in calls:
            self.statuses[
                f"{call.method} {re.sub(CODE, '{code}', call.path.split('?')[0])} "
                f"{call.status or 'failed'}"
            ] += 1
            if call.status and call.status < 400:
                continue
            if call.status == 0 and navigated:
                continue  # the app was closed with this request in flight
            if call.status and expected(call):
                continue
            self.fail(f"{name}'s app got an answer it does not expect: {call}")

    def closed(self, name: str, layer: dict[str, Any]) -> None:
        """Back closed the top layer: the overlay on top, or else the screen."""
        now = self.phones[name].page.evaluate(TOP_LAYER)
        if layer["overlay"]:
            still = self.phones[name].page.evaluate(
                "(id) => document.getElementById(id).classList.contains('show')", layer["overlay"]
            )
            if still:
                self.fail(f"Back left #{layer['overlay']} open on {name}'s phone (now {now})")
        elif now["screen"] == layer["screen"] and not now["overlay"]:
            self.fail(f"Back did not leave #{layer['screen']} on {name}'s phone")

    def agree(self) -> None:
        """Two phones in one game show the same game, once their polls settle.

        Each phone is held to what the server tells its own player: the
        same request its poll makes, answered for the same person.
        """
        a_game, b_game = self.games.get("Alice"), self.games.get("Bob")
        if not a_game or a_game != b_game:
            return
        kind, code = a_game
        screen = {"rooms": "deck", "steps69": "s69Board", "compat": "compatQuiz"}[kind]
        deadline = time.monotonic() + SETTLE_S
        last = ""
        while True:
            on_it = all(
                phone.page.evaluate(
                    "(s) => !!document.querySelector('section#' + s + '.active')"
                    " && !document.querySelector('.overlay.show')",
                    screen,
                )
                for phone in self.phones.values()
            )
            if not on_it:
                return
            states = {}
            for name, player in self.players.items():
                answer = player.call("GET", f"/api/{kind}/{code}")
                if answer.status_code != 200:
                    return  # gone or swept: nothing left to agree on
                states[name] = answer.json()
            last = getattr(self, f"_differ_{kind}")(states)
            if not last:
                return
            if time.monotonic() > deadline:
                break
            self.phones["Alice"].page.wait_for_timeout(500)
        self.fail(f"the two phones disagree about {kind} {code} after {SETTLE_S:.0f} s: {last}")

    def _differ_rooms(self, states: dict[str, dict[str, Any]]) -> str:
        if any(st["finished"] for st in states.values()):
            return ""
        for name, phone in self.phones.items():
            st = states[name]
            got = phone.page.evaluate(
                """() => ({
                coop: getComputedStyle(document.getElementById('turnChip')).display !== 'none',
                progress: """
                + PROGRESS_JS
                + """,
                text: (document.querySelector('#stage .card.top .q-text') || {}).innerText || '',
                mine: document.getElementById('turnChipText').classList.contains('turn-you'),
            })"""
            )
            if not got["coop"]:
                return ""  # a solo deck on the same screen: not this room
            want = f"{st['idx'] + 1} / {st['total']}"
            if got["progress"] != want or got["text"].split() != st["card_text"].split():
                return f"{name} shows card {got['progress']} {got['text'][:40]!r}; the room is on {want}"
            if got["mine"] != bool(st["started"] and st["your_turn"]):
                return f"{name}'s turn chip says {'' if got['mine'] else 'not '}their turn; the room disagrees"
        return ""

    def _differ_steps69(self, states: dict[str, dict[str, Any]]) -> str:
        for name, phone in self.phones.items():
            st = states[name]
            got = phone.page.evaluate("""() => {
                // A piece riding an arrow or a serpent is on no square yet.
                const at = (sel) => { const p = document.querySelector('#s69Map ' + sel);
                                      const cell = p && p.closest('.s69-cell');
                                      return cell ? Number(cell.dataset.id) : null; };
                return {mine: at('.s69-piece.mine'), theirs: at('.s69-piece:not(.mine)'),
                        rolling: document.getElementById('s69Dice').classList.contains('rolling'),
                        chip: document.getElementById('s69TurnChip').innerText
                                .replace(/\\u00a0/g, ' ').trim()};
            }""")
            if got["rolling"]:
                return f"{name}'s dice are still rolling"
            if got["mine"] != st["you"]["position"] or got["theirs"] != st["partner"]["position"]:
                return (
                    f"{name} sees their piece on {got['mine']} and the partner's on "
                    f"{got['theirs']}; the board has {st['you']['position']} and "
                    f"{st['partner']['position']}"
                )
            yours = (
                st["your_turn"]
                and st["started"]
                and not st["finished"]
                and not st["both_home"]
                and not st["you"]["home"]
            )
            if (got["chip"] == s69_your_turn(st["you"]["piece"])) != bool(yours):
                return (
                    f"{name}'s turn chip reads {got['chip']!r}; the board says "
                    f"{'' if yours else 'not '}their turn"
                )
        return ""

    def _differ_compat(self, states: dict[str, dict[str, Any]]) -> str:
        if any(st["finished"] for st in states.values()):
            return ""
        for name, phone in self.phones.items():
            st = states[name]
            want = f"Партнёр ответил на {st['partner_answered']} из {st['total']}"
            text = phone.text("#compatPartnerProgress")
            if text != want:
                return f"{name} reads {text!r}; the test holds {want!r}"
        return ""

    # -- the way home ----------------------------------------------------------

    def go_home(self) -> None:
        """However the evening went, each phone gets back to the home screen
        by Telegram's Back alone: the one way back every screen must offer,
        now that the header arrows hide wherever Telegram draws its own."""
        for name, phone in self.phones.items():
            for _ in range(12):
                layer = phone.page.evaluate(TOP_LAYER)
                if layer["screen"] == "home" and not layer["overlay"]:
                    break
                if not phone.back_button_visible():
                    self.fail(
                        f"{name} is on #{layer['overlay'] or layer['screen']} "
                        "and Telegram shows no Back button"
                    )
                self.say(
                    f"{name} on {layer['overlay'] or layer['screen']}: "
                    "Telegram's Back button, on the way home"
                )
                phone.press_back()
                phone.page.wait_for_timeout(500)
                self.check("back", name, layer)
            else:
                self.fail(f"{name} could not get back to the home screen")


def _seed(arena: str, run: int) -> int:
    if PINNED_SEED:
        return BASE_SEED
    return BASE_SEED + 7919 * run + ARENAS.index(arena)


@pytest.mark.parametrize("run", range(RUNS))
@pytest.mark.parametrize("arena", ARENAS)
def test_two_phones_survive_a_random_evening(
    server: Server, phones, device: Device, arena: str, run: int
) -> None:
    seed = _seed(arena, run)
    print(f"\nUI fuzz: seed {seed}, {arena} on {device.label}, {STEPS} steps")
    rng = random.Random(seed)
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    fuzz = UiFuzz(
        rng,
        seed,
        arena,
        device,
        phones={"Alice": phones(alice), "Bob": phones(bob)},
        players={"Alice": alice, "Bob": bob},
    )
    fuzz.setup()
    for _ in range(STEPS):
        fuzz.step()
    fuzz.go_home()
    fuzz.save()
    print(f"UI fuzz: seed {seed} passed: {dict(fuzz.counts)}; screens {dict(fuzz.screens)}")
