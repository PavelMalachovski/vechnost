"""Russian is the only language the product ships.

English and Czech are not deleted from history — they are one revert away —
but nothing in the running system may branch on language again without a
deliberate change here.
"""

from pathlib import Path

import pytest

from vechnost_bot.i18n import Language

DATA = Path(__file__).parent.parent / "data"


def test_only_russian_is_supported():
    assert [l.value for l in Language] == ["ru"]


@pytest.mark.parametrize("code", ["en", "cs", "de", "", None, "RU", "ru-RU"])
def test_any_stored_code_reads_as_russian(code):
    """Users carry `en` and `cs` in the database from before this change;
    reading one must not raise, it must quietly become Russian."""
    assert Language.coerce(code) is Language.RUSSIAN


@pytest.mark.parametrize("name", [
    "questions_en.yaml", "questions_cs.yaml",
    "translations_en.yaml", "translations_cs.yaml",
])
def test_retired_language_files_are_gone(name):
    assert not (DATA / name).exists()
