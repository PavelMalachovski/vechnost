"""The greeting is short enough to reach its button (audit D-34).

It used to run to about 1 900 characters - four manifesto sections, the deck
list, the features and a closing section - before the one button that
mattered, and half of it said again what «Что тебя ждёт внутри?» says one
tap away. Now: two sentences, the four decks in one line, the shared
features list, and the button.
"""

import re

from vechnost_bot.callback_handlers import features_block, welcome_screen
from vechnost_bot.i18n import Language

RU = Language.RUSSIAN


def _visible(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def test_the_greeting_fits_a_phone_screen_before_its_button():
    text, _ = welcome_screen(RU)
    assert len(_visible(text)) < 800


def test_it_says_what_vechnost_is_the_decks_and_everything_inside():
    text, _ = welcome_screen(RU)
    visible = _visible(text)
    assert visible.startswith("💎 VECHNOST\nКогда слова заканчиваются, начинается VECHNOST.")
    assert "Знакомство, Для пар, Секс и Провокации" in visible
    assert text.endswith(features_block(RU, bold=True)), "the pitch ends on the features"


def test_the_long_sections_are_behind_their_own_button_not_on_the_greeting():
    text, keyboard = welcome_screen(RU)
    for gone in ("СВЯЗЬ", "БЛИЗОСТЬ", "ИСКУССТВО БЛИЗОСТИ", "━━━"):
        assert gone not in text
    targets = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "show_inside" in targets and "show_why" in targets
