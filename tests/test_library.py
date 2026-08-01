"""Tests for the Library content loader and its YAML files."""

import pytest

from vechnost_bot.i18n import Language
from vechnost_bot.library import MODULES, Practice, load_practices


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
