"""The interface speaks to its reader as «вы»; only a partner says «ты».

The bot and the Mini App addressed the same person both ways: «Выберите
колоду» beside «Выбери тему», «✨ Твой ход», and a button reading «ЧТО ТЕБЯ
ЖДЁТ ВНУТРИ?» above a screen titled «Что вас ждёт в VECHNOST?» (audit
D-32). Nine strings in ten already said «вы», which also reads right when
two people hold one phone, so the interface says «вы».

«Ты» belongs to what one partner says to the other. The cards, the board
and the Joker are content, not interface, and outside this test. So is the
invitation a player sends from the app: the app only fills it in, and it is
the player's message to their partner.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parent.parent
TRANSLATIONS = ROOT / "data" / "translations_ru.yaml"
INDEX = ROOT / "webapp" / "index.html"

# What one partner sends the other, in the Mini App's I18N.
PARTNER_SPEECH = frozenset({"coopInviteMsg", "compatInviteMsg", "s69InviteMsg"})

_NOT_A_LETTER_BEFORE = r"(?<![А-Яа-яЁё])"
_NOT_A_LETTER_AFTER = r"(?![А-Яа-яЁё])"

TY = re.compile(
    _NOT_A_LETTER_BEFORE
    + r"(?:ты|тебя|тебе|тобой|тво[йяеёи]|твоего|твоей|твоих|твоим|твоими|твою)"
    + _NOT_A_LETTER_AFTER,
    re.IGNORECASE,
)

# The singular imperative of the verbs an interface uses: «нажми», «выбери».
IMPERATIVE_TY = re.compile(
    _NOT_A_LETTER_BEFORE + r"(?:нажми|выбери|открой|пригласи|отправь|поделись|начни|ответь|брось|"
    r"возьми|переверни|зайди|попробуй|вернись|подожди|жми|сыграй|пройди|"
    r"посмотри|смотри|листай|оплати|купи|напиши|скопируй|активируй|введи|"
    r"перешли|отметь|сохрани|задай|прочитай|читай|играй|держи|обнови)" + _NOT_A_LETTER_AFTER,
    re.IGNORECASE,
)


def _strings(node: Any, path: str = "") -> list[tuple[str, str]]:
    if isinstance(node, dict):
        return [pair for key, value in node.items() for pair in _strings(value, f"{path}.{key}")]
    if isinstance(node, list):
        return [pair for i, value in enumerate(node) for pair in _strings(value, f"{path}[{i}]")]
    return [(path.lstrip("."), node)] if isinstance(node, str) else []


def _bot_copy() -> list[tuple[str, str]]:
    return _strings(yaml.safe_load(TRANSLATIONS.read_text(encoding="utf-8")))


def _app_copy() -> list[tuple[str, str]]:
    """Every string in the Mini App's I18N literal, with the key it sits
    under - an array's strings (`payItems`) under the array's key. The
    literal's English comments are skipped whole: an apostrophe in one
    («button's») would otherwise open a string."""
    html = INDEX.read_text(encoding="utf-8")
    i18n = html.split("const I18N = {")[1].split("\n  };")[0]
    token = re.compile(r"'((?:[^'\\]|\\.)*)'|//[^\n]*|(\w+)\s*:")
    key, pairs = "", []
    for match in token.finditer(i18n):
        if match.group(2) is not None:
            key = match.group(2)
        elif match.group(1) is not None:
            pairs.append((key, match.group(1)))
    return pairs


def _says_ty(text: str) -> bool:
    return bool(TY.search(text) or IMPERATIVE_TY.search(text))


def test_the_bot_says_vy():
    offenders = [f"{key}: {text[:100]!r}" for key, text in _bot_copy() if _says_ty(text)]
    assert not offenders, "the bot addresses its reader as «ты»:\n" + "\n".join(offenders)


def test_the_mini_app_says_vy():
    copy = _app_copy()
    assert len(copy) > 150, "the I18N literal was not found where it used to be"
    offenders = [
        f"{key}: {text[:100]!r}"
        for key, text in copy
        if key not in PARTNER_SPEECH and _says_ty(text)
    ]
    assert not offenders, "the Mini App addresses its reader as «ты»:\n" + "\n".join(offenders)


def test_a_partner_still_says_ty():
    """The invitations are the one place the app writes «ты», on purpose."""
    speech = dict(_app_copy())
    for key in PARTNER_SPEECH:
        assert _says_ty(speech[key]), key


def test_no_button_shouts():
    """A button in capitals shouts over everything around it; the app's own
    buttons never did. Titles in a message keep their capitals."""
    buttons = [
        (key, text) for key, text in _bot_copy() if key.rsplit(".", 1)[-1].startswith("button_")
    ]
    assert buttons, "no bot buttons found"
    for key, text in buttons:
        letters = [c for c in text.replace("VECHNOST", "") if c.isalpha()]
        assert not letters or not all(c.isupper() for c in letters), (key, text)


def test_the_way_in_points_forward():
    """«Войти в VECHNOST ←» pointed back the way it was meant to lead."""
    start = dict(_bot_copy())["welcome.button_start"]
    assert "←" not in start and start.endswith("→")


def test_the_test_would_notice():
    for bad in ("Выбери тему", "✨ Твой ход", "ЧТО ТЕБЯ ЖДЁТ ВНУТРИ?", "Ты на 69-й."):
        assert _says_ty(bad), bad
    for good in (
        "Выберите тему",
        "✨ Ваш ход",
        "Что вас ждёт внутри?",
        "Вы на 69-й. Ждём партнёра.",
        "Смотрите, что внутри",
        "Итоги теста",
    ):
        assert not _says_ty(good), good
