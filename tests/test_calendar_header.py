"""The header above the calendar keyboard, pinned shape by shape.

`_calendar_header` is the one place six live handlers get this line from, and
until now nothing ran against it. It cannot be covered through those handlers:
every `async def test_` in this repo dies in collection on the session-scoped
`event_loop` fixture in conftest.py, so a green suite says nothing about them.
The builder is deliberately a plain synchronous function, which is what makes
it coverable here despite that.

The expected strings below are written out in full rather than assembled from
`get_text` calls. That is the point: assembling them from the same lookups the
builder uses would let a change to either sail through, and this is a test
about what the copy says. Assert the whole string, never a substring.
"""

import pytest

from vechnost_bot.callback_handlers import _calendar_header
from vechnost_bot.i18n import Language, get_text
from vechnost_bot.models import ContentType, SessionState, Theme

RU = Language.RUSSIAN

# Four shapes, and the differences between them are load-bearing:
#   - the Sex deck is titled by content type, never by level
#   - Provocation carries neither a level nor a count
#   - a levelled deck is a one-line title with NO card count
#   - only the levelless fallback spends a second line on the count, and it
#     names no level, because none was chosen
CASES = [
    (
        "sex questions",
        Theme.SEX, None, ContentType.QUESTIONS, 40,
        "🔥 Секс · Вопросы",
    ),
    (
        "sex tasks",
        Theme.SEX, None, ContentType.TASKS, 40,
        "🔥 Секс · Задания",
    ),
    (
        "provocation carries neither level nor count",
        Theme.PROVOCATION, None, ContentType.QUESTIONS, 34,
        "❤️‍🔥 Провокация",
    ),
    (
        "levelled deck is one line, no count",
        Theme.ACQUAINTANCE, 1, ContentType.QUESTIONS, 18,
        "✨ Знакомство · Уровень 1",
    ),
    (
        "levelled deck, another level",
        Theme.FOR_COUPLES, 3, ContentType.QUESTIONS, 7,
        "♥️ Для Пар · Уровень 3",
    ),
    (
        "levelless deck names no level and carries the count",
        Theme.FOR_COUPLES, None, ContentType.QUESTIONS, 30,
        "♥️ Для Пар\nОсталось карточек: 30",
    ),
    (
        "levelless deck, another theme",
        Theme.ACQUAINTANCE, None, ContentType.QUESTIONS, 18,
        "✨ Знакомство\nОсталось карточек: 18",
    ),
]

IDS = [c[0] for c in CASES]


def _session(theme: Theme, level: int | None) -> SessionState:
    return SessionState(language=RU, theme=theme, level=level)


@pytest.mark.parametrize("_name,theme,level,content_type,remaining,expected", CASES, ids=IDS)
def test_calendar_header_renders_each_shape(_name, theme, level, content_type, remaining, expected):
    assert _calendar_header(_session(theme, level), content_type, remaining) == expected


@pytest.mark.parametrize("_name,theme,level,content_type,remaining,expected", CASES, ids=IDS)
def test_calendar_header_never_leaves_trailing_whitespace(
    _name, theme, level, content_type, remaining, expected
):
    """The levelless header used to end on a dangling «Уровень » and a space.

    It came of formatting a `{level}` slot with "". The slot is gone now, but
    a header is assembled from several pieces and the next empty one would
    look exactly the same, so check every line of every shape.
    """
    header = _calendar_header(_session(theme, level), content_type, remaining)
    for line in header.split("\n"):
        assert line == line.rstrip(), f"trailing whitespace in {header!r}"
    assert header == header.strip()


def test_theme_and_its_qualifier_are_joined_by_the_middot():
    """Not a hyphen, and not an en dash.

    This line sits directly above a card image whose own footer is built by
    `_card_footer` as «Знакомство · 12/30». The two used to disagree — the
    header spent a long stretch on `-` while the card printed `·` — so the
    separator is the whole point of the assertion, not incidental to it.
    """
    levelled = _calendar_header(_session(Theme.ACQUAINTANCE, 1), ContentType.QUESTIONS, 18)
    assert " · " in levelled
    assert " - " not in levelled
    assert "–" not in levelled and "—" not in levelled


def test_the_levelless_header_does_not_name_a_level():
    """No level was chosen, so the word has no business being there.

    Guards the specific regression: `calendar.header` used to carry a
    `{level}` slot that every call site filled with "", rendering
    «♥️ Для Пар · Уровень » — a separator, a word, and nothing after it.
    """
    header = _calendar_header(_session(Theme.FOR_COUPLES, None), ContentType.QUESTIONS, 30)
    assert "Уровень" not in header
    assert "·" not in header
    assert header.split("\n") == ["♥️ Для Пар", "Осталось карточек: 30"]


def test_only_the_levelless_shape_carries_a_card_count():
    """A levelled deck's title has never had a count; keep it that way.

    This is the distinction that stopped the six duplicated blocks being
    collapsed into a single message. If someone later routes the levelled
    branch through `calendar.header` to save a key, this fails.
    """
    levelled = _calendar_header(_session(Theme.ACQUAINTANCE, 1), ContentType.QUESTIONS, 18)
    levelless = _calendar_header(_session(Theme.ACQUAINTANCE, None), ContentType.QUESTIONS, 18)
    assert "Осталось карточек" not in levelled
    assert "\n" not in levelled
    assert "Осталось карточек" in levelless


def test_the_level_word_in_the_header_matches_the_level_buttons():
    """«Уровень» is written twice, and the two copies must not drift.

    `level.level` is the button label — `keyboards.py` builds every level
    button as `f"{get_text('level.level', …)} {level}"`, and the Mini App
    mirrors it as `I18N.level`. `calendar.level_header` spells the same word
    out again inside its template.

    The duplication is deliberate: threading the word through as a third
    placeholder would make the template harder to read and translate than the
    sentence it renders, for one shared noun. What it costs is this failure
    mode — rename the word on the buttons and the header above them silently
    keeps the old one, on the same screen. That is what this test is for. If
    «Уровень» ever changes, change it in both places (and in the Mini App).
    """
    button_word = get_text("level.level", RU)
    template = get_text("calendar.level_header", RU)
    assert button_word in template, (
        f"{button_word!r} (level.level, used for the level buttons) no longer "
        f"appears in calendar.level_header ({template!r}) — the header and the "
        f"buttons under it have desynced"
    )
