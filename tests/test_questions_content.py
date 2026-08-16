"""Deck content invariants that must hold across all languages."""

import re
from pathlib import Path

import pytest
import yaml

DATA = Path(__file__).parent.parent / "data"
FILES = ["questions.yaml"]  # English and Czech decks are retired; see i18n.Language.

EXPECTED_SIZES = {
    ("Acquaintance", 1, "questions"): 30,
    ("Acquaintance", 2, "questions"): 30,
    ("Acquaintance", 3, "questions"): 33,
    ("For Couples", 1, "questions"): 30,
    ("For Couples", 2, "questions"): 30,
    ("For Couples", 3, "questions"): 30,
    ("Sex", None, "questions"): 79,
    ("Sex", None, "tasks"): 14,
    ("Provocation", None, "questions"): 34,
}


def _sizes(filename: str) -> dict:
    data = yaml.safe_load((DATA / filename).read_text(encoding="utf-8"))
    sizes = {}
    for theme, theme_data in data["themes"].items():
        if "levels" in theme_data:
            for level, level_data in theme_data["levels"].items():
                for kind, items in level_data.items():
                    sizes[(theme, level, kind)] = len(items)
        else:
            for kind, items in theme_data.items():
                sizes[(theme, None, kind)] = len(items)
    return sizes


@pytest.mark.parametrize("filename", FILES)
def test_deck_sizes_match_spec(filename):
    assert _sizes(filename) == EXPECTED_SIZES


def test_all_languages_have_identical_deck_sizes():
    reference = _sizes(FILES[0])
    for filename in FILES[1:]:
        assert _sizes(filename) == reference, f"{filename} diverged from {FILES[0]}"


def test_russian_provocation_uses_partnersha():
    data = yaml.safe_load((DATA / "questions.yaml").read_text(encoding="utf-8"))
    joined = " ".join(data["themes"]["Provocation"]["questions"])
    assert "партнёр(ка)" not in joined
    assert "партнёрша" in joined


# Any parenthetical suffix on "партнёр" — nominative or oblique, capitalised or
# not: партнёр(ка), Партнер(ка), партнером(кой), партнера(ку), партнера(ки)...
PARTNER_PARENTHETICAL = re.compile(r"[Пп]артн[её]р\w*\([а-яё]+\)")

# The one allowed survivor: its parenthetical is singular-vs-plural
# ("партнёру / партнёров"), not gender, so it is left as authored.
ALLOWED_PARTNER_PARENTHETICALS = [("Provocation", "questions", 23, "партнеру(ев)")]


def test_russian_partner_tokens_are_gendered_not_parenthetical():
    """Feminine agreement, not "партнёр(ка)"-style slashes, across the RU file."""
    data = yaml.safe_load((DATA / "questions.yaml").read_text(encoding="utf-8"))
    found = []
    for theme, theme_data in data["themes"].items():
        decks = (
            [(f"{theme} L{lv}", d) for lv, d in theme_data["levels"].items()]
            if "levels" in theme_data
            else [(theme, theme_data)]
        )
        for label, deck in decks:
            for kind, items in deck.items():
                for position, text in enumerate(items, 1):
                    for token in PARTNER_PARENTHETICAL.findall(text):
                        found.append((label, kind, position, token))
    assert found == ALLOWED_PARTNER_PARENTHETICALS, found


@pytest.mark.parametrize("filename", FILES)
def test_no_duplicate_questions_within_a_deck(filename):
    data = yaml.safe_load((DATA / filename).read_text(encoding="utf-8"))
    for theme, theme_data in data["themes"].items():
        decks = (
            [(f"{theme} L{lv}", d) for lv, d in theme_data["levels"].items()]
            if "levels" in theme_data
            else [(theme, theme_data)]
        )
        for label, deck in decks:
            for kind, items in deck.items():
                assert len(set(items)) == len(items), f"{label} {kind} has duplicates"
