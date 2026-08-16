"""No em dashes in the content or the interface copy.

The card sets text at a large size on a narrow measure, where an em dash
opens a hole in the line. Where the punctuation is genuinely needed the
content uses an en dash instead; where it was standing in for a comma or a
colon, the sentence was rewritten. The bot's Russian UI strings follow the
same rule, so `data/translations_ru.yaml` is guarded outright.

`webapp/index.html` cannot be: most of its long dashes live in English code
comments, where they are correct English punctuation. So the Mini App is
guarded only across the surface a user reads — the `<title>` and the `I18N`
literal — sliced out the way the sibling tests in test_webapp_static.py slice
function bodies.

The en dash U+2013 is the sanctioned replacement and is deliberately absent
from BANNED below. Everything else that renders as a long horizontal stroke
is banned, so that a copy-paste from another editor cannot smuggle one back
in under a different codepoint.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CONTENT = sorted(
    [ROOT / "data" / "questions.yaml", ROOT / "data" / "translations_ru.yaml"]
    + list((ROOT / "data" / "library").glob("*.yaml"))
)
INDEX = ROOT / "webapp" / "index.html"

BANNED = {
    "—": "U+2014 em dash",
    "―": "U+2015 horizontal bar",
    "−": "U+2212 minus sign",
    "⸺": "U+2E3A two-em dash",
    "⸻": "U+2E3B three-em dash",
    "﹘": "U+FE58 small em dash",
    "︱": "U+FE31 vertical em dash",
    "－": "U+FF0D fullwidth hyphen-minus",
}


@pytest.mark.parametrize("path", CONTENT, ids=lambda p: p.name)
def test_content_has_no_em_dash(path):
    text = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.name}:{n}: [{name}] {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        for char, name in BANNED.items()
        if char in line
    ]
    assert not offenders, "long dash left in:\n" + "\n".join(offenders)


def _user_facing_html() -> dict[str, str]:
    """The parts of the Mini App a user reads, keyed by what they are.

    Everything outside these two slices is either markup or English prose
    written for whoever is editing the file next.
    """
    html = INDEX.read_text(encoding="utf-8")
    return {
        "<title>": html.split("<title>", 1)[1].split("</title>", 1)[0],
        "I18N": html.split("const I18N = {", 1)[1].split("\n  };", 1)[0],
    }


@pytest.mark.parametrize("surface", ["<title>", "I18N"])
def test_the_mini_app_user_copy_has_no_em_dash(surface):
    text = _user_facing_html()[surface]
    offenders = [
        f"index.html {surface}: [{name}] {line.strip()}"
        for line in text.splitlines()
        for char, name in BANNED.items()
        if char in line
    ]
    assert not offenders, "long dash left in:\n" + "\n".join(offenders)


def test_the_mini_app_slices_are_the_ones_we_think_they_are():
    """A slice that silently missed would make the guard above vacuous."""
    surfaces = _user_facing_html()
    assert "Vechnost" in surfaces["<title>"]
    i18n = surfaces["I18N"]
    assert "paywallText:" in i18n and "compatIntro:" in i18n
    # The literal ends before the next top-level constant.
    assert "THEME_ORDER" not in i18n and "CARD_ART" not in i18n
