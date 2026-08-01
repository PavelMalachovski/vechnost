"""Tests for the Library content loader and its YAML files."""

import pytest

from vechnost_bot.i18n import Language
from vechnost_bot.library import (
    MODULES,
    LibraryCategory,
    Practice,
    load_categories,
    load_practices,
)

DATE_CATEGORY_SIZES = {
    "home": 25,
    "outdoors": 25,
    "culture": 25,
    "extreme": 15,
    "food": 10,
    "deep": 15,
    "spicy": 10,
    "spontaneous": 25,
}


def test_practice_modules_are_registered():
    assert MODULES["practices_self"].type == "practice"
    assert MODULES["practices_self"].paid is False
    assert MODULES["practices_couples"].paid is True


@pytest.mark.parametrize("module_id", ["practices_self", "practices_couples"])
def test_practice_module_has_25_complete_items(module_id):
    items = load_practices(module_id, Language.RUSSIAN)
    assert len(items) == 25
    for item in items:
        assert isinstance(item, Practice)
        assert item.title.strip()
        assert item.why.strip()
        assert item.result.strip()


def test_module_count_matches_loaded_items():
    assert MODULES["practices_self"].count == len(
        load_practices("practices_self", Language.RUSSIAN)
    )


def test_non_russian_falls_back_to_russian():
    ru = load_practices("practices_self", Language.RUSSIAN)
    en = load_practices("practices_self", Language.ENGLISH)
    assert en == ru


def test_unknown_module_raises():
    with pytest.raises(KeyError):
        load_practices("nope", Language.RUSSIAN)


def test_dates_has_eight_categories_with_expected_sizes():
    categories = load_categories("dates", Language.RUSSIAN)
    assert {c.id: len(c.items) for c in categories} == DATE_CATEGORY_SIZES
    assert sum(len(c.items) for c in categories) == 150


def test_only_the_spicy_category_is_nsfw():
    categories = load_categories("dates", Language.RUSSIAN)
    assert [c.id for c in categories if c.nsfw] == ["spicy"]


def test_fall_in_love_is_one_category_of_36():
    categories = load_categories("fall_in_love", Language.RUSSIAN)
    assert len(categories) == 1
    assert len(categories[0].items) == 36
    assert categories[0].nsfw is False


def test_every_category_item_is_non_empty():
    for module_id in ("dates", "fall_in_love"):
        for category in load_categories(module_id, Language.RUSSIAN):
            assert isinstance(category, LibraryCategory)
            assert all(item.strip() for item in category.items)


def test_module_counts_match_loaded_categories():
    for module_id in ("dates", "fall_in_love"):
        loaded = sum(len(c.items) for c in load_categories(module_id, Language.RUSSIAN))
        assert MODULES[module_id].count == loaded


def test_no_duplicate_ideas_within_a_category():
    for category in load_categories("dates", Language.RUSSIAN):
        assert len(set(category.items)) == len(category.items), category.id
