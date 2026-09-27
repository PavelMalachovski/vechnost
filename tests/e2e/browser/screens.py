"""Every screen of the Mini App, on each phone, at four sizes.

A `Tour` walks one phone model through the whole app - the deck, the 18+
gate and the paywall, a room from its door to a finished deck, the
compatibility test from its door to the result, «69 ступеней» from its door
to the finale, the Library, a practice and the masterclass - and at every
stop resizes the page through four phone screens, handing each one to the
visitors: a screenshot, and whatever else wants to look at every screen.
Two-player states are reached for real: a partner joins through the API and
the phone catches up through its own poll.

`write_contact_sheet` lays the screenshots of every phone out as one HTML
page, and a Markdown table for CI's job summary.
"""

from __future__ import annotations

import html
import json
import os
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from vechnost_bot.compat import TOTAL_QUESTIONS

from ..harness import Player, Server, code_from_invite
from .app import (
    THEME_NAMES,
    cards,
    longest_card,
    open_deck,
    remember,
    resize,
    settle_card,
    wait_home,
)
from .phones import REPORT_DIR, Device, Engines, Phone, open_phone

# The phones people hold, small to large: iPhone SE, iPhone 8, iPhone 15 Pro,
# iPhone 15 Pro Max. The Androids in between fall inside the same range.
VIEWPORTS = [(320, 568), (375, 667), (393, 852), (430, 932)]
POLL = 15_000  # a phone hears a partner through its ~2.5 s poll
SCREENS_DIR = REPORT_DIR / "screens"
# A toast is a moment, not a screen: it is hidden from the pictures.
SHOT_STYLE = "#toast { visibility: hidden !important; }"

# (id, what the contact sheet calls it), in the order the tour reaches them.
STOPS = [
    ("home", "Home"),
    ("themes", "Themes"),
    ("levels", "Levels"),
    ("deck", "A deck card"),
    ("deck-long", "The longest card, scrolled to its end"),
    ("nsfw", "The 18+ question"),
    ("paywall", "The paywall after the free cards"),
    ("coop", "Room: its door"),
    ("room-waiting", "Room: waiting for the partner"),
    ("room-playing", "Room: playing"),
    ("room-finished", "Room: the deck is done"),
    ("compat", "Compatibility test: its door"),
    ("compat-invite", "Compatibility test: waiting for the partner"),
    ("compat-question", "Compatibility test: a question"),
    ("compat-result", "Compatibility test: the result"),
    ("s69-entry", "69: its door"),
    ("s69-invite", "69: waiting for the partner"),
    ("s69-board", "69: the board"),
    ("s69-cell-info", "69: a square's action"),
    ("s69-finale", "69: the finale"),
    ("s69-done", "69: the path is walked"),
    ("library", "Practices (the Library)"),
    ("library-detail", "A module's categories"),
    ("practice", "A practice deck"),
    ("guide", "The masterclass"),
]

Viewport = tuple[int, int]


def vp_name(viewport: Viewport) -> str:
    return f"{viewport[0]}x{viewport[1]}"


@dataclass
class Atlas:
    """What one tour saw: a screenshot per stop and viewport, and notes."""

    device: Device
    shots: dict[str, dict[str, str]] = field(default_factory=dict)
    # Whatever the other visitors recorded, by stop and viewport.
    notes: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    reached: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def missing(self) -> list[str]:
        return [stop for stop, _ in STOPS if stop not in self.reached]

    def note(self, stop: str, viewport: Viewport, key: str, value: Any) -> None:
        self.notes.setdefault(stop, {}).setdefault(vp_name(viewport), {})[key] = value


Visitor = Callable[[Atlas, str, Phone, Viewport], None]


class Tour:
    """One phone model, walked through every screen."""

    def __init__(
        self,
        engines: Engines,
        base_url: str,
        server: Server,
        device: Device,
        visitors: list[Visitor] | None = None,
    ) -> None:
        self.engines = engines
        self.base_url = base_url
        self.server = server
        self.device = device
        self.out = SCREENS_DIR / device.name
        self.atlas = Atlas(device)
        self.visitors: list[Visitor] = [self._screenshot, *(visitors or [])]
        self.phones: list[Phone] = []
        # Alice has paid and Bob has not; Pat is the partner on the other
        # phone, who joins and plays through the API.
        self.alice = server.player("Alice", paid=True)
        self.bob = server.player("Bob")
        self.pat = server.player("Pat")
        self.room = self.test = self.game = ""

    # -- the walk ------------------------------------------------------------

    def run(self) -> Atlas:
        started = time.monotonic()
        self.out.mkdir(parents=True, exist_ok=True)
        try:
            self.paid = self._phone(self.alice)
            self.free = self._phone(self.bob)
            self.current = self.paid
            for stop, _ in STOPS:
                getattr(self, "stop_" + stop.replace("-", "_"))()
                self._visit(stop)
                self.atlas.reached.append(stop)
        except Exception as e:
            self.atlas.errors.append(
                f"the tour stopped before {self.atlas.missing[0]!r}: "
                + "".join(traceback.format_exception_only(type(e), e)).strip()
            )
            try:
                self.current.shot(f"stuck-before-{self.atlas.missing[0]}")
            except Exception:
                pass
        finally:
            for phone in self.phones:
                self.atlas.errors.extend(f"{phone.name}: {error}" for error in phone.errors)
                phone.context.close()
            self.atlas.seconds = time.monotonic() - started
        return self.atlas

    def _phone(self, player: Player) -> Phone:
        phone = open_phone(
            self.engines, self.base_url, player, shots=self.out / "steps",
            device=self.device, trace=False,
        )
        self.phones.append(phone)
        wait_home(phone)
        return phone

    def _visit(self, stop: str) -> None:
        phone = self.current
        own = {"width": self.device.width, "height": self.device.height}
        prepare = getattr(self, "prepare_" + stop.replace("-", "_"), None)
        for viewport in VIEWPORTS:
            resize(phone, {"width": viewport[0], "height": viewport[1]})
            phone.page.wait_for_selector("#loader:not(.show)", state="attached", timeout=15_000)
            if prepare:
                prepare()
            for visitor in self.visitors:
                visitor(self.atlas, stop, phone, viewport)
        resize(phone, own)

    def _screenshot(self, atlas: Atlas, stop: str, phone: Phone, viewport: Viewport) -> None:
        name = f"{stop}@{vp_name(viewport)}.png"
        phone.page.evaluate("() => document.fonts.ready.then(() => true)")
        phone.page.screenshot(
            path=str(self.out / name), animations="disabled", caret="hide",
            scale="css", style=SHOT_STYLE,
        )
        atlas.shots.setdefault(stop, {})[vp_name(viewport)] = f"{self.device.name}/{name}"

    def _fresh(self, phone: Phone) -> None:
        """Close the app and open it again: a clean screen, the same storage."""
        phone.open_link(None)
        wait_home(phone)
        self.current = phone

    def _age(self, phone: Phone) -> None:
        """Say yes to the 18+ question if it is asked."""
        try:
            phone.page.wait_for_selector("#nsfw.show", timeout=1_500)
        except Exception:
            return
        phone.tap("#nsfwYes")

    # -- the stops -----------------------------------------------------------
    # Each leaves `self.current` on the screen it is named after.

    def stop_home(self) -> None:
        self.current = self.paid

    def stop_themes(self) -> None:
        self.paid.tap("#btnPlay")
        self.paid.screen("themes")

    def stop_levels(self) -> None:
        self.paid.page.locator(
            "#themeList .theme-card", has_text=THEME_NAMES["Acquaintance"]
        ).first.tap()
        self.paid.screen("levels")

    def stop_deck(self) -> None:
        self.paid.page.locator("#levelList .level-card").first.tap()
        self.paid.screen("deck")
        settle_card(self.paid)

    def stop_deck_long(self) -> None:
        self._fresh(self.paid)
        open_deck(self.paid, longest_card(self.alice))

    def prepare_deck_long(self) -> None:
        self.paid.page.evaluate("""() => {
            const z = document.querySelector('#stage .card.top .q-zone');
            z.scrollTop = z.scrollHeight;
        }""")
        self.paid.page.wait_for_timeout(250)  # the fades follow the scroll

    def stop_nsfw(self) -> None:
        self.current = self.free
        self.free.tap("#btnPlay")
        self.free.screen("themes")
        self.free.page.locator("#themeList .theme-card", has_text=THEME_NAMES["Sex"]).first.tap()
        self.free.page.wait_for_selector("#nsfw.show")

    def stop_paywall(self) -> None:
        self.free.tap("#nsfwNo")
        last_free = [c for c in cards(self.bob) if c.theme == "Sex" and c.kind == "questions"][-1]
        remember(self.free, "nsfwOk", True)
        remember(self.free, "deck." + last_free.deck_key, {
            "order": list(range(last_free.deck_size)), "idx": last_free.index, "shuffled": False,
        })
        self.free.page.locator("#themeList .theme-card", has_text=THEME_NAMES["Sex"]).first.tap()
        self.free.screen("deck")
        settle_card(self.free)
        self.free.tap("#btnNext")
        self.free.page.wait_for_selector("#paywall.show")

    def stop_coop(self) -> None:
        self._fresh(self.paid)
        self.paid.tap("#btnCoop")
        self.paid.screen("coop")

    def stop_room_waiting(self) -> None:
        self.paid.tap("#btnCoopCreate")
        self.paid.screen("themes")
        self.paid.page.locator(
            "#themeList .theme-card", has_text=THEME_NAMES["Acquaintance"]
        ).first.tap()
        self.paid.screen("levels")
        self.paid.page.locator("#levelList .level-card").first.tap()
        self.paid.screen("invite")
        self.room = code_from_invite(self.paid.text("#inviteCode"))

    def stop_room_playing(self) -> None:
        self.pat.ok("POST", f"/api/rooms/{self.room}/join")
        self.paid.screen("deck", timeout=POLL)
        settle_card(self.paid)

    def stop_room_finished(self) -> None:
        for _ in range(400):
            state = self.alice.ok("GET", f"/api/rooms/{self.room}")
            if state["finished"]:
                break
            mover = self.alice if state["your_turn"] else self.pat
            mover.ok("POST", f"/api/rooms/{self.room}/advance")
        self.paid.page.wait_for_selector("#done.show", timeout=POLL)

    def stop_compat(self) -> None:
        self._fresh(self.paid)
        self.paid.tap("#btnCompat")
        self.paid.screen("compat")

    def stop_compat_invite(self) -> None:
        self.paid.tap("#btnCompatCreate")
        self.paid.screen("compatInvite")
        self.test = code_from_invite(self.paid.text("#compatCode"))

    def stop_compat_question(self) -> None:
        self.pat.ok("POST", f"/api/compat/{self.test}/join", {})
        self.paid.screen("compatQuiz", timeout=POLL)

    def stop_compat_result(self) -> None:
        # Close on most spheres and far apart on some, so the result has
        # something in every section.
        for index in range(TOTAL_QUESTIONS):
            mine = 5 if index % 3 else 2
            theirs = 5 if index % 4 else 1
            self.alice.ok("POST", f"/api/compat/{self.test}/answer", {"index": index, "value": mine})
            self.pat.ok("POST", f"/api/compat/{self.test}/answer", {"index": index, "value": theirs})
        self.paid.screen("compatResult", timeout=POLL)

    def stop_s69_entry(self) -> None:
        self._fresh(self.paid)
        self.paid.tap("#btnS69")
        self._age(self.paid)
        self.paid.screen("s69")
        self.paid.page.wait_for_selector("#s69Suits button")

    def stop_s69_invite(self) -> None:
        self.paid.page.locator("#s69Suits button").first.tap()
        self.paid.tap("#btnS69Duo")
        self.paid.screen("s69Invite")
        self.game = code_from_invite(self.paid.text("#s69Code"))

    def stop_s69_board(self) -> None:
        self.pat.ok("POST", f"/api/steps69/{self.game}/join", {})
        self.paid.screen("s69Board", timeout=POLL)

    def stop_s69_cell_info(self) -> None:
        self.paid.tap('#s69Map [data-id="4"]')
        self.paid.page.wait_for_selector("#s69CellInfo.show")

    def stop_s69_finale(self) -> None:
        self.paid.tap("#s69InfoClose")
        for _ in range(600):
            state = self.alice.ok("GET", f"/api/steps69/{self.game}")
            if state["both_home"]:
                break
            mover = self.alice if state["your_turn"] else self.pat
            mover.ok("POST", f"/api/steps69/{self.game}/roll")
        self.paid.page.wait_for_selector("#s69Finale.show", timeout=POLL)

    def stop_s69_done(self) -> None:
        self.paid.tap("#s69FinaleChoices button")
        self.paid.page.wait_for_selector("#s69Done.show", timeout=POLL)

    def stop_library(self) -> None:
        self._fresh(self.paid)
        self.paid.tap("#btnPractices")
        self.paid.screen("library")
        self.paid.page.wait_for_selector("#libraryList [data-module]")

    def stop_library_detail(self) -> None:
        self.paid.tap('#libraryList [data-module="dates"]')
        self.paid.screen("libraryDetail")

    def stop_practice(self) -> None:
        # Telegram's Back, not the header arrow: the arrow hides wherever
        # Telegram has a Back button of its own.
        self.paid.press_back()
        self.paid.screen("library")
        self.paid.tap('#libraryList [data-module="practices_couples"]')
        self.paid.screen("libDeck")
        settle_card(self.paid, "#libStage")

    def stop_guide(self) -> None:
        self._fresh(self.paid)
        self.paid.tap('#homeModules [data-module="nude_guide"]')
        self.paid.screen("guide")
        self.paid.page.wait_for_selector("#guideBody .guide-step")


# -- the contact sheet -------------------------------------------------------


def save_atlas(atlas: Atlas) -> None:
    """Record one phone's tour next to its pictures, and redraw the sheet."""
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "device": atlas.device.name,
        "title": atlas.device.title,
        "engine": atlas.device.engine,
        "shots": atlas.shots,
        "notes": atlas.notes,
        "missing": atlas.missing,
        "errors": atlas.errors,
        "seconds": round(atlas.seconds, 1),
    }
    (SCREENS_DIR / f"{atlas.device.name}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_contact_sheet()


def _manifests() -> list[dict[str, Any]]:
    found = []
    for path in sorted(SCREENS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(data, dict) and "shots" in data:
            found.append(data)
    return found


def write_contact_sheet() -> None:
    """screens/index.html (every picture) and screens/summary.md (the table)."""
    phones = _manifests()
    columns = [(p, vp_name(v)) for p in phones for v in VIEWPORTS]
    head = "".join(
        f"<th>{html.escape(p['device'])} · {html.escape(p['engine'])}<br>{v}</th>"
        for p, v in columns
    )
    rows = []
    for stop, title in STOPS:
        cells = []
        for p, v in columns:
            shot = p["shots"].get(stop, {}).get(v)
            cells.append(
                f'<td><a href="{html.escape(shot)}"><img loading="lazy" src="{html.escape(shot)}" '
                f'alt="{html.escape(stop)} {v}"></a></td>' if shot else '<td class="none">–</td>'
            )
        rows.append(f"<tr><th>{html.escape(title)}<br><code>{stop}</code></th>{''.join(cells)}</tr>")
    problems = "".join(
        f"<li><b>{html.escape(p['device'])}</b>: {html.escape(error)}</li>"
        for p in phones for error in p.get("errors", [])
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VECHNOST screens</title>
<style>
  body {{ font: 14px/1.4 system-ui, sans-serif; margin: 16px; background: #f6f3f5; color: #222; }}
  table {{ border-collapse: collapse; }}
  th, td {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; background: #fff; }}
  thead th {{ position: sticky; top: 0; z-index: 1; }}
  tbody th {{ text-align: left; max-width: 160px; position: sticky; left: 0; }}
  img {{ width: 150px; display: block; }}
  td.none {{ color: #aaa; text-align: center; }}
  .problems {{ color: #a00; }}
</style></head><body>
<h1>VECHNOST screens</h1>
<p>Every screen of the Mini App on each phone at four sizes. Toasts are hidden and
animations stopped. Click a picture for full size.</p>
{f'<ul class="problems">{problems}</ul>' if problems else ''}
<table><thead><tr><th>Screen</th>{head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>
"""
    (SCREENS_DIR / "index.html").write_text(page, encoding="utf-8")

    artifact = os.environ.get("E2E_ARTIFACT_NAME", "")
    lines = ["### Screens", ""]
    if artifact:
        lines += [f"Artifact `{artifact}`: open `browser/screens/index.html` for every picture.", ""]
    names = [vp_name(v) for v in VIEWPORTS]
    lines += ["| Screen | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for stop, _ in STOPS:
        cells = []
        for v in names:
            got = [f"{p['device']} ({p['engine']})" for p in phones if p["shots"].get(stop, {}).get(v)]
            cells.append(", ".join(got) or "missing")
        lines.append(f"| `{stop}` | " + " | ".join(cells) + " |")
    total = sum(len(shots) for p in phones for shots in p["shots"].values())
    lines += ["", f"{len(STOPS)} screens × {len(VIEWPORTS)} sizes × "
              f"{len(phones)} phone(s): {total} screenshots."]
    for p in phones:
        for error in p.get("errors", []):
            lines.append(f"- **{p['device']}**: {error.splitlines()[0]}")
    (SCREENS_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
