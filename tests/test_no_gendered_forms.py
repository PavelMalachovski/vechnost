"""User-facing text must not decide the reader's gender.

Russian past-tense and short-adjective forms carry gender, and the app does
not know the reader's. The old workaround was a bracket — «уверен(а)»,
«ответил(а)» — which reads as a form to fill in and still puts the masculine
first. Present and future tense carry no gender at all, and neither do
«мне удалось», «случалось ли тебе», a nominalisation («в чём проявилась моя
щедрость») or agreement with a noun («партнёр изменил», «был ли у тебя
опыт»). Those are the tools; this test is the fence.

Scope is the text a person reads: the content YAML, the bot's translations,
and the Mini App's own strings. Code comments are exempt — they are English
prose about Russian text, and «he/she» in a comment is not shown to anyone.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

CONTENT = [
    ROOT / "data" / "questions.yaml",
    ROOT / "data" / "steps69_ru.yaml",
    ROOT / "data" / "translations_ru.yaml",
    *sorted((ROOT / "data" / "library").glob("*.yaml")),
]

INDEX = ROOT / "webapp" / "index.html"

# «уверен(а)», «сделал(а)», «неидеальным(ой)», «он(а)», «поленился(лась)».
BRACKETED = re.compile(r"[А-Яа-яЁё]\((?:а|ла|лась|ась|лся|ой|ей|ою|на|у|ы|и|л)\)")

# A first- or second-person verb in the past tense, which is the other way
# the text can pick a gender: «ты сделал», «я была».
PERSONAL_PAST = re.compile(
    r"(?<![А-Яа-яЁё])(?:ты|я)\s+(?:не\s+)?[А-Яа-яЁё]+(?:л|ла|лся|лась)(?![А-Яа-яЁё])",
    re.IGNORECASE,
)

# The third dodge, and the one a bracket check walks straight past:
# «проснулся/проснулась», «верен/верна». Same problem, a slash instead of
# parentheses, and it still makes the reader pick a side.
SLASHED = re.compile(
    r"[А-Яа-яЁё]{3,}(?:ся|л|н|а|о)?/[А-Яа-яЁё]{3,}(?:лась|ась|на|ла)(?![А-Яа-яЁё])"
)


def _lines(path):
    """Content lines, minus the YAML comments, with 1-based numbers."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        yield number, line


@pytest.mark.parametrize("path", CONTENT, ids=lambda p: p.name)
def test_content_never_picks_a_gender_for_the_reader(path):
    offenders = [
        f"{path.name}:{number}: {line.strip()[:120]}"
        for number, line in _lines(path)
        if (BRACKETED.search(line) or PERSONAL_PAST.search(line)
            or SLASHED.search(line))
    ]
    assert not offenders, "gendered form in user-facing text:\n" + "\n".join(offenders)


def _mini_app_copy():
    """The two surfaces of index.html a user actually reads.

    Same split test_no_em_dash makes: the title and the I18N literal. The
    rest of the file is code and English comments.
    """
    html = INDEX.read_text(encoding="utf-8")
    title = html.split("<title>")[1].split("</title>")[0]
    i18n = html.split("const I18N = {")[1].split("\n  };")[0]
    return title, i18n


def test_the_mini_app_copy_never_picks_a_gender():
    for chunk in _mini_app_copy():
        for line in chunk.splitlines():
            assert not BRACKETED.search(line), line.strip()
            assert not PERSONAL_PAST.search(line), line.strip()
            assert not SLASHED.search(line), line.strip()


def test_the_test_would_notice():
    """A fence nobody can see the shape of is not a fence."""
    assert BRACKETED.search("Ты уверен(а) в этом?")
    assert BRACKETED.search("Что бы ты сделал(а)?")
    assert PERSONAL_PAST.search("Когда ты понял это?")
    assert PERSONAL_PAST.search("Я была там вчера")
    assert SLASHED.search("Ради чего я проснулся/проснулась?")
    assert SLASHED.search("За что я благодарен/благодарна себе?")
    # And what the rewrites actually use must pass.
    for good in (
        "Что ты будешь делать, если партнёр обидит питомца?",
        "Случалось ли тебе имитировать оргазм?",
        "В чём сегодня проявилась моя щедрость?",
        "Был ли у тебя опыт эротического массажа?",
        "Ты узнаёшь, что партнёр изменил тебе. Какова твоя реакция?",
    ):
        assert not BRACKETED.search(good), good
        assert not PERSONAL_PAST.search(good), good
        assert not SLASHED.search(good), good
