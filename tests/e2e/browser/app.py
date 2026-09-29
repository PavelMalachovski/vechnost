"""Walking the Mini App: the few paths every browser test takes.

Everything here goes through the app's own screens and its own storage -
the saved deck position the app resumes from, the 18+ confirmation it
remembers - rather than reaching into its closure, so a test sees what a
person holding the phone would see.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...wording import plain
from ..harness import Player
from .phones import Phone

# The deck names the app prints on its theme cards (I18N.themes), in the
# order it lists them (THEME_ORDER).
THEME_NAMES = {
    "Acquaintance": "Знакомство",
    "For Couples": "Для пар",
    "Sex": "Секс",
    "Provocation": "Провокация",
}

TOP_CARD = "#stage .card.top"
# The smallest phone the app is laid out for (iPhone SE): where a card that
# fits a big screen still has to be scrolled.
SMALLEST = {"width": 320, "height": 568}


@dataclass(frozen=True)
class Card:
    """One card of one deck, as the API serves it to a player."""

    theme: str
    level: str | None
    kind: str  # "questions" / "tasks"
    index: int
    deck_size: int
    text: str

    @property
    def deck_key(self) -> str:
        """The key the app saves this deck's position under (deckKey())."""
        return "|".join(["ru", self.theme, self.level or "0", self.kind])


def cards(player: Player) -> list[Card]:
    """Every card this player's app is sent, deck by deck."""
    themes = player.ok("GET", "/api/questions")["themes"]
    found: list[Card] = []
    for theme, entry in themes.items():
        decks: list[tuple[str | None, dict[str, Any]]] = (
            [(level, deck) for level, deck in sorted(entry["levels"].items())]
            if "levels" in entry
            else [(None, entry)]
        )
        for level, deck in decks:
            for kind in ("questions", "tasks"):
                items = deck.get(kind) or []
                found.extend(
                    Card(theme, level, kind, i, len(items), text) for i, text in enumerate(items)
                )
    return found


def longest_card(player: Player) -> Card:
    return max(cards(player), key=lambda card: len(card.text))


def wait_home(phone: Phone) -> None:
    """The home screen, with its preload finished and its module rows drawn."""
    phone.screen("home")
    phone.page.wait_for_selector("#loader:not(.show)", state="attached", timeout=15_000)
    phone.page.wait_for_selector("#homeModules button", timeout=15_000)


def remember(phone: Phone, key: str, value: Any) -> None:
    """Put a value in the app's own storage (its `store`, `vech.` keys)."""
    phone.page.evaluate(
        "([k, v]) => localStorage.setItem('vech.' + k, v)", [key, json.dumps(value)]
    )


def settle_card(phone: Phone, stage: str = "#stage") -> None:
    """Wait until the top card has turned face up and stopped moving."""
    phone.page.wait_for_function(
        """(stage) => {
            const card = document.querySelector(stage + ' .card.top');
            const flipper = card && card.querySelector('.flipper');
            if (!flipper || flipper.classList.contains('faced')) return false;
            const turned = getComputedStyle(flipper).transform;
            return (turned === 'none' || turned === 'matrix(1, 0, 0, 1, 0, 0)')
                && !card.style.transform;
        }""",
        arg=stage,
        timeout=10_000,
    )


def open_deck(phone: Phone, card: Card, *, confirm_age: bool = True) -> None:
    """Open `card`'s deck on that card, the way the app resumes a deck."""
    if confirm_age:
        remember(phone, "nsfwOk", True)
    remember(
        phone,
        "deck." + card.deck_key,
        {
            "order": list(range(card.deck_size)),
            "idx": card.index,
            "shuffled": False,
        },
    )
    phone.tap("#btnPlay")
    phone.screen("themes")
    phone.page.locator("#themeList .theme-card", has_text=THEME_NAMES[card.theme]).first.tap()
    if card.level is not None:
        phone.screen("levels")
        phone.page.locator("#levelList .level-card").nth(int(card.level) - 1).tap()
    phone.screen("deck")
    mode = "#modeQ" if card.kind == "questions" else "#modeT"
    if phone.page.is_visible("#modeRow") and "on" not in (
        phone.page.get_attribute(mode, "class") or ""
    ):
        phone.tap(mode)
    settle_card(phone)
    shown = phone.text(f"{TOP_CARD} .q-text")
    assert shown.split() == card.text.split(), f"opened {shown[:60]!r}, not {card.text[:60]!r}"


def zone(phone: Phone, stage: str = "#stage") -> dict[str, float]:
    """The top card's text band: where it is, and how far it can scroll."""
    return dict(
        phone.page.evaluate(
            """(stage) => {
            const z = document.querySelector(stage + ' .card.top .q-zone');
            const r = z.getBoundingClientRect();
            return {x: r.left + r.width / 2, y: r.top + r.height / 2,
                    width: r.width, height: r.height, scrollTop: z.scrollTop,
                    slack: z.scrollHeight - z.clientHeight};
        }""",
            stage,
        )
    )


# Which way a finger throws the top card: left is «дальше», right goes back,
# as in a gallery.
LEFT, RIGHT = -1, 1

# The cards lying beneath the top one that the eye can see: the one a swipe
# would bring. The card before is laid there too, hidden until a drag goes
# right.
BENEATH_JS = """(stage) => [...document.querySelectorAll(stage + ' .card.under')]
    .filter(el => getComputedStyle(el).visibility !== 'hidden')
    .map(el => el.querySelector('.q-text').innerText)"""


def swipe(
    phone: Phone,
    direction: int,
    stage: str = "#stage",
    hold: Callable[[], None] | None = None,
) -> None:
    """Throw the top card LEFT or RIGHT across its text band; `hold` runs with
    the finger still down, at the end of the throw."""
    band = zone(phone, stage)
    x, y, width = band["x"], band["y"], band["width"]
    phone.finger.drag(
        (x - direction * width * 0.3, y), (x + direction * width * 0.45, y + 8), hold=hold
    )


def beneath(phone: Phone, stage: str = "#stage") -> list[str]:
    """The text of each card the eye can see beneath the top one."""
    return [plain(text).strip() for text in phone.page.evaluate(BENEATH_JS, stage)]


def open_module(phone: Phone, module: str) -> None:
    """A Library module's deck, entered from «Практики»."""
    phone.tap("#btnPractices")
    phone.screen("library")
    phone.page.wait_for_selector("#libraryList [data-module]")
    phone.tap(f'#libraryList [data-module="{module}"]')
    phone.screen("libDeck")
    settle_card(phone, "#libStage")


def resize(phone: Phone, viewport: dict[str, int]) -> None:
    """Turn the page into a phone of another size, and let it lay out."""
    phone.page.set_viewport_size(viewport)
    phone.page.evaluate(
        "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )
    phone.page.wait_for_timeout(150)


# Where the deck is, as "6 / 30". The only counter a person sees is on the
# card («Карта 6 из 30», audit D-30); this reads the bar above it, which
# carries the same two numbers for a screen reader and does not fly away
# with the card mid-swipe. An expression, for the tests' own predicates.
PROGRESS_JS = (
    "(() => { const bar = document.getElementById('progressTrack');"
    " return bar.getAttribute('aria-valuenow') + ' / ' + bar.getAttribute('aria-valuemax'); })()"
)


# The board's turn chip on the phone whose turn it is: the player's own suit,
# then «Ваш ход» (audit D-39: it led with a sparkle, an emoji on a board that
# has none). The suit is held to the words by a no-break space.
S69_SUIT = {"hearts": "♥", "spades": "♠", "clubs": "♣", "diamonds": "♦"}
S69_CHIP = (
    "t => document.querySelector('#s69TurnChip')?.innerText.replace(/\\u00a0/g, ' ').trim() === t"
)


def s69_your_turn(piece: str) -> str:
    return f"{S69_SUIT[piece]} Ваш ход"


def progress(phone: Phone) -> str:
    return str(phone.page.evaluate("() => " + PROGRESS_JS))
