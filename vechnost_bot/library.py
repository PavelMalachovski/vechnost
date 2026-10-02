"""Library content: date ideas, practices, and reflection prompts.

Content is Russian-only in this phase; other languages fall back to the
Russian file. This module deliberately imports neither FastAPI nor
python-telegram-bot so it can be used from the web API, the bot, and tests
alike.
"""

import re
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from .i18n import Language
from .paths import DATA

LIBRARY_DIR = DATA / "library"
# The masterclass's pictures: one WebP per `art` key, rendered from a scene
# by scripts/render_guide_art.py and served by the Library API under the
# guide's own rules, never as static files.
GUIDE_ART_DIR = LIBRARY_DIR / "art"
_ART_KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Practice(BaseModel):
    title: str
    why: str
    result: str


class LibraryCategory(BaseModel):
    id: str
    title: str
    nsfw: bool = False
    items: list[str]


class GuideItem(BaseModel):
    """One thing to do, with the picture that shows how it looks."""

    id: str
    title: str
    text: str
    # The key of the picture the Mini App shows beside the text
    # (data/library/art/<module>/<key>.webp). Every item carries one, and
    # `test_library.py` checks each has its picture: a missing one leaves
    # an empty frame that reads as a layout fault.
    art: str
    tips: list[str] = []


class GuideStep(BaseModel):
    """One numbered rung of a guide, so a reader knows where they are."""

    id: str
    number: int
    title: str
    lead: str
    nsfw: bool = False
    items: list[GuideItem]


class LibraryModule(BaseModel):
    id: str
    title: str
    emoji: str
    type: Literal["list", "practice", "daily", "guide"]
    paid: bool
    count: int


MODULES: dict[str, LibraryModule] = {
    m.id: m
    for m in [
        LibraryModule(
            id="dates", title="Идеи для свиданий", emoji="💡", type="list", paid=True, count=150
        ),
        LibraryModule(
            id="fall_in_love",
            title="36 вопросов, чтобы влюбиться",
            emoji="💘",
            type="list",
            paid=False,
            count=36,
        ),
        LibraryModule(
            id="practices_self",
            title="Практики для себя",
            emoji="🌱",
            type="practice",
            paid=False,
            count=25,
        ),
        LibraryModule(
            id="practices_couples",
            title="Практики для пар",
            emoji="💞",
            type="practice",
            paid=True,
            count=25,
        ),
        LibraryModule(
            id="nude_guide",
            title="Мастер-класс по нюдсам",
            emoji="📸",
            type="guide",
            paid=True,
            count=28,
        ),
        LibraryModule(
            id="reflection", title="Вопрос дня", emoji="🌙", type="daily", paid=False, count=365
        ),
    ]
}


@cache
def _load_yaml(module_id: str, language: Language) -> dict:
    """Parsed YAML for a module. Non-Russian languages fall back to Russian."""
    if module_id not in MODULES:
        raise KeyError(module_id)
    path = LIBRARY_DIR / f"{module_id}_{language.value}.yaml"
    if not path.exists():
        path = LIBRARY_DIR / f"{module_id}_ru.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_practices(module_id: str, language: Language = Language.RUSSIAN) -> list[Practice]:
    """The practices of a `practice`-type module, in authored order."""
    data = _load_yaml(module_id, language)
    return [Practice(**item) for item in data.get("items", [])]


def load_guide(module_id: str, language: Language = Language.RUSSIAN) -> list[GuideStep]:
    """The numbered steps of a `guide`-type module, in authored order."""
    data = _load_yaml(module_id, language)
    return [GuideStep(**step) for step in data.get("steps", [])]


def guide_art_path(module_id: str, key: str) -> Path | None:
    """The picture for a guide item's `art` key, or None if there is none.

    A key is looked up by name, never used as a path: anything that is not
    lowercase words joined by hyphens is refused before it touches the disk.
    """
    if module_id not in MODULES or not _ART_KEY.match(key):
        return None
    path = GUIDE_ART_DIR / module_id / f"{key}.webp"
    return path if path.is_file() else None


def guide_intro(module_id: str, language: Language = Language.RUSSIAN) -> str:
    """The paragraph a guide opens on, before its first step."""
    return str(_load_yaml(module_id, language).get("intro", ""))


def load_categories(module_id: str, language: Language = Language.RUSSIAN) -> list[LibraryCategory]:
    """The categories of a `list`-type module, in authored order."""
    data = _load_yaml(module_id, language)
    return [LibraryCategory(**category) for category in data.get("categories", [])]


REFLECTION_TOTAL = 365


def load_reflection(language: Language = Language.RUSSIAN) -> list[list[str]]:
    """The twelve blocks of reflection prompts, in order."""
    data = _load_yaml("reflection", language)
    return [block["items"] for block in data.get("blocks", [])]


def question_of_the_day(day_of_year: int, language: Language = Language.RUSSIAN) -> tuple[str, int]:
    """
    The reflection prompt for a day of the year, plus its 1-based number.

    Day 366 of a leap year wraps back to the first prompt: one repeated day
    beats carrying a 366th question that is unused three years in four.

    Wrapping on the actual number of prompts rather than on REFLECTION_TOTAL
    keeps a short YAML from raising IndexError — the daily push renders
    outside its try block, so one bad index would cancel the whole job.
    """
    flat = [q for block in load_reflection(language) for q in block]
    index = (day_of_year - 1) % len(flat)
    return flat[index], index + 1
