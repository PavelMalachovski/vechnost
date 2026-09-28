"""A short word stays with the word after it, a dash with the word before
(audit D-31), on the bot's cards, in its messages and in the Mini App.

The rule is written twice, in vechnost_bot/typography.py and as
`bindShortWords` in webapp/index.html, because the app wraps its own text in
the browser. The test runs both on one list of lines through node, so the
two cannot drift apart.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vechnost_bot.i18n import Language, get_text
from vechnost_bot.renderer import _pick_font_path, layout_text
from vechnost_bot.typography import NBSP, binds, nbsp, units

from .test_card_layout import DECK

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "webapp" / "index.html"

LINES = [
    "и в доме",
    "а и в доме тепло",
    "Я люблю тебя – и всё",
    "5 карт и 69 ступеней",
    "«в доме» с котом",
    "Готов ли ты",
    "2026 год",
    "Нажмите на клетку, чтобы прочитать её действие",
    "Идеи для свиданий, практики для пар и вопрос дня",
    "без тебя",
    "Партнёр в игре. Ваш ход!",
    "Ответ – да",
    "It is a test",
    "",
]


def test_a_short_word_keeps_the_next_one():
    assert nbsp("и в доме") == f"и{NBSP}в{NBSP}доме"
    assert nbsp("Идеи для свиданий") == f"Идеи для{NBSP}свиданий"
    assert nbsp("5 карт") == f"5{NBSP}карт"
    assert nbsp("2026 год") == "2026 год", "a year is not a short word"
    assert nbsp("Готов ли ты") == f"Готов ли{NBSP}ты"


def test_a_dash_keeps_the_word_before_it():
    assert nbsp("Я люблю тебя – и всё") == f"Я{NBSP}люблю тебя{NBSP}– и{NBSP}всё"


def test_a_tag_is_left_alone():
    """`<a href>` has a one-letter word in it too."""
    assert nbsp("<a href='x'>в доме</a> и мы") == f"<a href='x'>в{NBSP}доме</a> и{NBSP}мы"
    assert nbsp("<b>С нами</b>") == f"<b>С{NBSP}нами</b>"


def test_binding_twice_changes_nothing():
    for line in LINES:
        assert nbsp(nbsp(line)) == nbsp(line), line


def test_the_renderer_breaks_between_units_only():
    assert units("Я люблю тебя – и всё в доме") == ["Я люблю", "тебя –", "и всё", "в доме"]
    assert binds("«в") and binds("для") and not binds("дом")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_mini_app_binds_exactly_as_the_bot_does():
    html = INDEX.read_text(encoding="utf-8")
    block = html.split("// typography:start")[1].split("// typography:end")[0]
    lines = json.dumps(LINES, ensure_ascii=False)
    script = f"{block}\nprocess.stdout.write(JSON.stringify({lines}.map(bindShortWords)));"
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60, check=True
    )
    assert json.loads(result.stdout) == [nbsp(line) for line in LINES]


def test_the_bots_messages_are_bound():
    """Bound once, where the translations are read."""
    assert f"по{NBSP}вашим приглашениям" in get_text(
        "referral.invite_no_discount", Language.RUSSIAN
    )


def test_no_line_of_a_card_ends_on_a_short_word():
    """Every card in the deck, as the bot lays it out: a line may end on a
    word that keeps the next one only if it is the text's last line."""
    offenders = []
    for _background, text in DECK:
        lines = layout_text(text, _pick_font_path(text), has_footer=True).lines
        for line in lines[:-1]:
            last = line.split()[-1]
            if binds(last):
                offenders.append(f"{line!r} in {text[:60]!r}")
    assert not offenders, "\n".join(offenders[:20])
