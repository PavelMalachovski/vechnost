"""Tests for the Library content loader and its YAML files."""

import pytest

from vechnost_bot.i18n import Language
from vechnost_bot.library import (
    MODULES,
    REFLECTION_TOTAL,
    LibraryCategory,
    Practice,
    guide_intro,
    load_categories,
    load_guide,
    load_practices,
    load_reflection,
    question_of_the_day,
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


def test_unsupported_code_coerces_to_russian():
    """The YAML-fallback behaviour this replaced is no longer reachable from
    outside `library.py` now that `Language` has one member; this pins the
    `Language.coerce` fallback that stands in for it."""
    assert Language.coerce("en") is Language.RUSSIAN


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


def test_the_nude_guide_is_five_numbered_steps():
    """Numbered so a reader knows where they are and what comes next, rather
    than a flat list they have to sequence themselves."""
    steps = load_guide("nude_guide", Language.RUSSIAN)
    assert [s.number for s in steps] == [1, 2, 3, 4, 5]
    assert [s.id for s in steps] == ["light", "camera", "her", "him", "edit"]
    assert {s.id: len(s.items) for s in steps} == {
        "light": 4, "camera": 3, "her": 10, "him": 10, "edit": 2
    }


def test_only_the_pose_steps_of_the_nude_guide_are_nsfw():
    """Light, camera, editing and safety are craft, not nudity: gating them
    behind an age confirmation would hide the part that keeps people safe."""
    steps = load_guide("nude_guide", Language.RUSSIAN)
    assert [s.id for s in steps if s.nsfw] == ["her", "him"]


def test_every_guide_item_carries_a_drawing():
    """The Mini App renders `art` as a schematic beside the words. A blank
    key draws nothing and reads as a layout fault, so none may be blank."""
    for step in load_guide("nude_guide", Language.RUSSIAN):
        for item in step.items:
            assert item.art.strip(), f"{step.id}/{item.id} has no art key"
            assert item.title.strip() and item.text.strip()


def test_guide_art_keys_are_unique():
    """Two items sharing a key would silently show the same picture."""
    keys = [i.art for s in load_guide("nude_guide", Language.RUSSIAN) for i in s.items]
    assert len(keys) == len(set(keys))


def test_the_guide_opens_with_something_to_read():
    assert guide_intro("nude_guide", Language.RUSSIAN).strip()


def test_the_nude_guide_says_something_about_safety():
    """The guide asks people to photograph themselves undressed. It does not
    get to skip the part about what happens to the pictures afterwards."""
    steps = load_guide("nude_guide", Language.RUSSIAN)
    last = next(s for s in steps if s.id == "edit")
    privacy = next(i for i in last.items if i.id == "privacy")
    assert privacy.text.strip() and len(privacy.tips) >= 2
    assert not last.nsfw, "the safety advice must sit in front of the age gate"


def test_the_module_count_matches_the_guide():
    assert MODULES["nude_guide"].count == sum(
        len(s.items) for s in load_guide("nude_guide", Language.RUSSIAN)
    )
    assert MODULES["nude_guide"].type == "guide"


def test_no_duplicate_ideas_within_a_category():
    for category in load_categories("dates", Language.RUSSIAN):
        assert len(set(category.items)) == len(category.items), category.id


BLOCK_SIZES = [31, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 34]


def test_reflection_has_twelve_blocks_summing_to_365():
    blocks = load_reflection(Language.RUSSIAN)
    assert [len(b) for b in blocks] == BLOCK_SIZES
    assert sum(len(b) for b in blocks) == REFLECTION_TOTAL == 365


def test_first_and_last_question_of_the_year():
    blocks = load_reflection(Language.RUSSIAN)
    assert question_of_the_day(1, Language.RUSSIAN) == (blocks[0][0], 1)
    assert question_of_the_day(365, Language.RUSSIAN) == (blocks[11][33], 365)


def test_leap_day_wraps_to_the_first_question():
    text, day = question_of_the_day(366, Language.RUSSIAN)
    assert (text, day) == question_of_the_day(1, Language.RUSSIAN)


def test_question_of_the_day_is_deterministic():
    assert question_of_the_day(200, Language.RUSSIAN) == question_of_the_day(
        200, Language.RUSSIAN
    )


def test_no_duplicate_reflection_questions():
    flat = [q for block in load_reflection(Language.RUSSIAN) for q in block]
    assert len(set(flat)) == len(flat)
