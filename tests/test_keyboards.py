"""The deck's keyboards in the bot: every button does something (audit D-33).

Three things looked like buttons and were not: blank cells padding the
calendar out to 7x4 (sixteen of them on a short last page), the page counter
«Страница 1 из 2», and the card counter «4 из 30» beside «Назад» - all
`noop`, all styled exactly like the buttons that work. And the calendar's
«Предыдущий» read «← ← Предыдущий»: the label carries its own arrow and the
keyboard added a second. The counts live in the text now (the calendar's
message, the card's own footer).
"""

from tests.wording import plain
from vechnost_bot.callback_handlers import _calendar_text
from vechnost_bot.i18n import Language
from vechnost_bot.keyboards import get_calendar_keyboard, get_question_keyboard
from vechnost_bot.models import ContentType, SessionState, Theme

RU = Language.RUSSIAN


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _calendar(page: int, total_items: int):
    items = [f"card {i}" for i in range(total_items)]
    total_pages = (total_items + 27) // 28
    return get_calendar_keyboard("prov", 0, "q", page, items, total_pages, False, RU)


def test_no_button_does_nothing():
    for markup in (
        _calendar(0, 34),
        _calendar(1, 34),
        _calendar(0, 20),
        get_question_keyboard("prov", 0, 0, 34, RU),
        get_question_keyboard("prov", 0, 12, 34, RU),
        get_question_keyboard("prov", 0, 0, 1, RU),
    ):
        for button in _buttons(markup):
            assert button.callback_data != "noop", button.text
            assert button.text.strip(), "a blank cell"


def test_a_short_last_page_shows_only_its_cards():
    markup = _calendar(1, 34)  # the last six of 34
    numbers = [b.text for b in _buttons(markup) if b.text.isdigit()]
    assert numbers == [str(n) for n in range(29, 35)]
    assert [len(row) for row in markup.inline_keyboard[:1]] == [6]


def test_a_full_page_is_four_rows_of_seven():
    rows = _calendar(0, 34).inline_keyboard
    assert [len(row) for row in rows[:4]] == [7, 7, 7, 7]


def test_the_arrow_is_printed_once():
    labels = [b.text for b in _buttons(_calendar(1, 34))]
    assert "← Предыдущий" in labels
    assert not any(label.startswith("← ←") for label in labels)
    assert "Следующий →" in [b.text for b in _buttons(_calendar(0, 34))]


def test_the_page_is_named_in_the_text_when_there_is_more_than_one():
    session = SessionState(theme=Theme.PROVOCATION, language=RU)
    assert plain(_calendar_text(session, ContentType.QUESTIONS, 34, 1, 2)) == (
        "❤️‍🔥 Провокация\nСтраница 2 из 2"
    )
    assert _calendar_text(session, ContentType.QUESTIONS, 20, 0, 1) == "❤️‍🔥 Провокация"


def test_the_card_keyboard_is_the_way_on_and_the_way_back():
    first = get_question_keyboard("prov", 0, 0, 34, RU).inline_keyboard
    assert [[b.text for b in row] for row in first] == [["Следующий →"], ["← Назад"]]

    middle = get_question_keyboard("prov", 0, 12, 34, RU).inline_keyboard
    assert [[b.text for b in row] for row in middle] == [
        ["← Предыдущий", "Следующий →"],
        ["← Назад"],
    ]

    only = get_question_keyboard("prov", 0, 0, 1, RU).inline_keyboard
    assert [[b.text for b in row] for row in only] == [["← Назад"]], "no empty row"
