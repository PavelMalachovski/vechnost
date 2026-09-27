"""Russian is the only language the product ships.

English and Czech are not deleted from history — they are one revert away —
but nothing in the running system may branch on language again without a
deliberate change here.
"""

import asyncio
import json
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from vechnost_bot.i18n import Language
from vechnost_bot.models import ContentType, Theme
from vechnost_bot.storage import RedisSessionStore

DATA = Path(__file__).parent.parent / "data"


def test_only_russian_is_supported():
    assert [language.value for language in Language] == ["ru"]


@pytest.mark.parametrize("code", ["en", "cs", "de", "", None, "RU", "ru-RU"])
def test_any_stored_code_reads_as_russian(code):
    """Users carry `en` and `cs` in the database from before this change;
    reading one must not raise, it must quietly become Russian."""
    assert Language.coerce(code) is Language.RUSSIAN


def test_coerce_returns_a_typed_member_by_lookup_not_by_luck():
    """`Language` subclasses `str`, so `str(Language.RUSSIAN)` is
    `"Language.RUSSIAN"`: an already-typed member falls to the `except`
    branch and comes back as Russian by accident, not by lookup. With one
    member the two are indistinguishable, so pin the behaviour against a
    stand-in enum that borrows the same `coerce` and *does* have a second
    member — there, "by accident" gives the wrong answer.
    """
    class TwoLanguages(str, Enum):
        RUSSIAN = "ru"
        ENGLISH = "en"

        coerce = Language.__dict__["coerce"]

    assert Language.coerce(Language.RUSSIAN) is Language.RUSSIAN
    assert TwoLanguages.coerce(TwoLanguages.ENGLISH) is TwoLanguages.ENGLISH


def test_a_session_stored_in_a_retired_language_survives_the_round_trip():
    """A stored session is rebuilt from a JSON dict, and one written before
    the product went Russian-only carries `en`.

    Without `Language.coerce` the model refuses the value and the stored
    session is discarded: theme, level, drawn cards and the 18+ confirmation
    gone, mid-game, on every read until the TTL expires.

    Synchronous on purpose, driven through `asyncio.run`.
    """
    storage = RedisSessionStore("redis://localhost:6379/0", ttl=60)
    storage._client = AsyncMock()
    storage._client.get = AsyncMock(return_value=json.dumps({
        "theme": "Acquaintance",
        "level": 2,
        "content_type": "questions",
        "drawn_cards": ["уже вытянутая карта", "и вторая"],
        "is_nsfw_confirmed": True,
        "language": "en",
    }))

    session = asyncio.run(storage.get_session(4242))

    assert session is not None, "the stored session was discarded"
    assert session.language is Language.RUSSIAN
    assert session.theme is Theme.ACQUAINTANCE
    assert session.level == 2
    assert session.content_type is ContentType.QUESTIONS
    assert session.drawn_cards == {"уже вытянутая карта", "и вторая"}
    assert session.is_nsfw_confirmed is True


@pytest.mark.parametrize("name", [
    "questions_en.yaml", "questions_cs.yaml",
    "translations_en.yaml", "translations_cs.yaml",
])
def test_retired_language_files_are_gone(name):
    assert not (DATA / name).exists()


def test_the_bot_no_longer_offers_a_language_choice():
    """`/start` opens on the welcome screen; there is nothing to choose."""
    src = Path(__file__).parent.parent / "vechnost_bot"

    assert not (src / "language_keyboards.py").exists()
    for name in ("handlers.py", "callback_handlers.py", "keyboards.py"):
        text = (src / name).read_text(encoding="utf-8")
        assert "language_keyboards" not in text, f"{name} still imports it"
        assert "get_language_selection_keyboard" not in text
