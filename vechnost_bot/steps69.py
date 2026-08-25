"""«Территория искушения: 69 ступеней»: доска, переходы и Джокер.

Deliberately imports neither FastAPI nor python-telegram-bot, exactly like
`library.py` and `compat.py`, so the web API, the bot and the tests all use
this module directly.

Two rules are worth stating up front, because both differ from the board
game the mechanic borrows from:

* **Overshooting does not bounce.** Rolling past 69 lands on 69. A pair in
  the middle of sex should not be sent backwards on a technicality, and the
  last cells are a run-up to the finale rather than a target to hit exactly.
* **Portals never chain.** Every ladder and snake target is an ordinary
  cell, so one roll moves at most twice: the dice, then the portal.
  `test_steps69.py` holds that invariant, because a portal landing on a
  portal would loop here.

Secrets do not live in the board payload. `board_view` strips them, and the
text reaches exactly one player through `cell_view`: the one who rolled onto
the cell. That is the mechanic ("уникальным для каждого игрока") and also
the only way to keep it out of the other partner's devtools.
"""

import random
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from .i18n import Language

CONTENT_DIR = Path(__file__).parent.parent / "data"

BOARD_SIZE = 69
START_CELL = 1
DICE_SIDES = 6

# Every tenth cell asks the pair to say what is turning them on right now.
# Only ordinary cells carry it: cell 50 is a Joker, and stacking a generated
# task and a milestone prompt on one screen buries both.
MILESTONE_EVERY = 10
MILESTONE_KINDS = frozenset({"step", "secret"})

# A pair covering more than this many cells per roll is being carried by the
# ladders rather than playing. The Joker answers that by slowing them down
# with a tender task, whatever stage of the board they are standing on.
RUSH_CELLS_PER_TURN = 5.0

# Where each third of the board sits, for choosing a Joker's register.
Stage = Literal["tender", "drive", "ecstasy"]
STAGE_BOUNDS: tuple[int, int] = (23, 46)

CellKind = Literal["start", "step", "secret", "joker", "ladder", "snake", "final"]


class Cell(BaseModel):
    id: int
    kind: CellKind
    title: str
    text: str = ""
    # Secret cells only. `secret` is what the player who rolled here reads;
    # `partner` is the one line the other player gets instead.
    secret: str | None = None
    partner: str | None = None
    # Ladder and snake cells only: where the piece actually ends up.
    to: int | None = None

    @property
    def is_portal(self) -> bool:
        return self.kind in ("ladder", "snake")

    @property
    def is_milestone(self) -> bool:
        return self.id % MILESTONE_EVERY == 0 and self.kind in MILESTONE_KINDS


class Block(BaseModel):
    id: str
    title: str
    subtitle: str
    first: int
    last: int


class JokerTask(BaseModel):
    id: str
    title: str
    text: str


class FinaleChoice(BaseModel):
    id: str
    title: str
    text: str


class Finale(BaseModel):
    title: str
    intro: str
    choices: list[FinaleChoice]
    outro: str


class Move(BaseModel):
    """One roll, from the square left behind to the square stood on."""

    start: int
    roll: int
    landed: int          # where the dice put the piece, before any portal
    position: int        # where it ended up
    event: Literal["ladder", "snake"] | None = None
    message: str | None = None

    @property
    def moved_by_portal(self) -> bool:
        return self.event is not None


@cache
def _content(language: Language) -> dict:
    """Parsed board. Non-Russian falls back to the Russian file."""
    path = CONTENT_DIR / f"steps69_{language.value}.yaml"
    if not path.exists():
        path = CONTENT_DIR / "steps69_ru.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@cache
def load_cells(language: Language = Language.RUSSIAN) -> tuple[Cell, ...]:
    """All 69 cells, indexable by `cells[id - 1]`. Raises if the board is malformed."""
    cells = tuple(Cell(**c) for c in _content(language).get("cells", []))
    if len(cells) != BOARD_SIZE:
        raise ValueError(f"the board must hold {BOARD_SIZE} cells, found {len(cells)}")
    if [c.id for c in cells] != list(range(1, BOARD_SIZE + 1)):
        raise ValueError("cells must be numbered 1..69 in order")
    return cells


def cell(number: int, language: Language = Language.RUSSIAN) -> Cell:
    """The cell standing at `number`. Raises IndexError outside the board."""
    if not START_CELL <= number <= BOARD_SIZE:
        raise IndexError(f"cell {number} is off the board")
    return load_cells(language)[number - 1]


@cache
def load_blocks(language: Language = Language.RUSSIAN) -> tuple[Block, ...]:
    return tuple(Block(**b) for b in _content(language).get("blocks", []))


@cache
def portals(language: Language = Language.RUSSIAN) -> dict[int, int]:
    """Every ladder and snake, read off the cells that declare them."""
    return {c.id: c.to for c in load_cells(language) if c.is_portal and c.to}


def ladders(language: Language = Language.RUSSIAN) -> dict[int, int]:
    return {c.id: c.to for c in load_cells(language) if c.kind == "ladder" and c.to}


def snakes(language: Language = Language.RUSSIAN) -> dict[int, int]:
    return {c.id: c.to for c in load_cells(language) if c.kind == "snake" and c.to}


def system_text(key: str, language: Language = Language.RUSSIAN) -> str:
    return str(_content(language).get("system", {}).get(key, ""))


@cache
def load_finale(language: Language = Language.RUSSIAN) -> Finale:
    return Finale(**_content(language)["finale"])


@cache
def load_jokers(language: Language = Language.RUSSIAN) -> dict[str, tuple[JokerTask, ...]]:
    raw = _content(language).get("jokers", {})
    return {stage: tuple(JokerTask(**t) for t in tasks) for stage, tasks in raw.items()}


def joker_task(task_id: str, language: Language = Language.RUSSIAN) -> JokerTask | None:
    for tasks in load_jokers(language).values():
        for task in tasks:
            if task.id == task_id:
                return task
    return None


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------

def roll_dice(rng: random.Random | None = None) -> int:
    return (rng or random).randint(1, DICE_SIDES)


def resolve_move(
    start: int, roll: int, language: Language = Language.RUSSIAN
) -> Move:
    """Where one roll leaves the piece, portal included.

    Overshooting 69 lands on 69 rather than bouncing back: see the module
    docstring. A portal fires once and cannot chain, because no portal
    target is itself a portal.
    """
    if not START_CELL <= start <= BOARD_SIZE:
        raise ValueError(f"cannot move from cell {start}")
    if not 1 <= roll <= DICE_SIDES:
        raise ValueError(f"a die shows 1..{DICE_SIDES}, not {roll}")

    landed = min(start + roll, BOARD_SIZE)
    here = cell(landed, language)
    if here.to and here.kind in ("ladder", "snake"):
        event: Literal["ladder", "snake"] = here.kind
        return Move(
            start=start,
            roll=roll,
            landed=landed,
            position=here.to,
            event=event,
            message=here.text or system_text(event, language),
        )
    return Move(start=start, roll=roll, landed=landed, position=landed)


# ---------------------------------------------------------------------------
# The Joker
# ---------------------------------------------------------------------------

def stage_of(position: int) -> Stage:
    """Which third of the board a position sits in."""
    tender_last, drive_last = STAGE_BOUNDS
    if position <= tender_last:
        return "tender"
    if position <= drive_last:
        return "drive"
    return "ecstasy"


def is_rushing(position: int, turns: int) -> bool:
    """Whether the pair is being carried through the board rather than playing."""
    if turns <= 0:
        return False
    return (position - START_CELL) / turns > RUSH_CELLS_PER_TURN


def pick_joker(
    position: int,
    turns: int,
    used: list[str] | None = None,
    language: Language = Language.RUSSIAN,
    rng: random.Random | None = None,
) -> JokerTask:
    """A task for a Joker cell: by stage, unless the pair needs slowing down.

    Tasks already handed out this game are skipped, so a pair that lands on
    all three Jokers gets three different tasks. Once a stage's pool is
    exhausted it repeats rather than failing.
    """
    stage: Stage = "tender" if is_rushing(position, turns) else stage_of(position)
    pool = load_jokers(language).get(stage) or ()
    if not pool:
        raise ValueError(f"no joker tasks for stage {stage}")

    spent = set(used or ())
    fresh = [task for task in pool if task.id not in spent] or list(pool)
    return (rng or random).choice(fresh)


# ---------------------------------------------------------------------------
# What each player is allowed to see
# ---------------------------------------------------------------------------

def board_view(language: Language = Language.RUSSIAN) -> dict:
    """The map: enough to draw 69 squares, nothing that spoils them.

    Titles and portal arrows only. A cell's instruction reaches a player
    when their piece is standing on it and not before, so the deck cannot be
    read ahead through the network tab.
    """
    return {
        "size": BOARD_SIZE,
        "title": _content(language).get("title", ""),
        "subtitle": _content(language).get("subtitle", ""),
        "age": _content(language).get("age", "18+"),
        "blocks": [b.model_dump() for b in load_blocks(language)],
        "cells": [
            {
                "id": c.id,
                "kind": c.kind,
                "title": c.title,
                "to": c.to,
                "milestone": c.is_milestone,
            }
            for c in load_cells(language)
        ],
        "system": _content(language).get("system", {}),
    }


Audience = Literal["mover", "partner", "shared"]


def cell_view(
    position: int,
    audience: Audience,
    joker_task_id: str | None = None,
    language: Language = Language.RUSSIAN,
) -> dict:
    """One cell as one audience may see it.

    "mover" is the player who rolled onto this cell and "partner" is the one
    watching: on a secret cell the mover reads the instruction and the
    partner reads their own line, and neither is ever sent the other's.
    "shared" is the one-phone game, where both halves go to the same screen
    because there is no second device to withhold anything from.

    A Joker always carries the task the server already drew rather than a
    fresh one, so two phones polling the same game agree on what was dealt.
    """
    if audience not in ("mover", "partner", "shared"):
        raise ValueError(f"unknown audience {audience!r}")

    here = cell(position, language)
    view: dict = {
        "id": here.id,
        "kind": here.kind,
        "title": here.title,
        "text": here.text,
        "milestone": here.is_milestone,
        "milestone_text": system_text("milestone", language) if here.is_milestone else None,
    }

    if here.kind == "secret":
        view["secret"] = here.secret if audience in ("mover", "shared") else None
        view["partner"] = here.partner if audience in ("partner", "shared") else None
        view["secret_locked"] = system_text("secret_locked", language)

    if here.kind == "joker":
        task = joker_task(joker_task_id, language) if joker_task_id else None
        view["joker"] = task.model_dump() if task else None

    if here.kind == "final":
        view["finale"] = load_finale(language).model_dump()

    return view
