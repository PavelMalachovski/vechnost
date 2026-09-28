"""The Mini App's web fonts: one file per face, holding what the app sets.

The page used to declare two files per face, Google's Cyrillic subset and
its Latin one, and the Latin one weighed three times the Cyrillic - Latin-1
letters, a page of punctuation and their alternates - for a page whose Latin
is its digits, its punctuation and the name VECHNOST (audit D-41). Now each
face is one file cut by `scripts/fetch_webapp_fonts.py`, and these tests
read what each file really holds rather than what the stylesheet says about
it: a face missing a character the copy uses would draw that character in
the phone's own font, which no other test would notice.
"""

from __future__ import annotations

import importlib.util
import re
import unicodedata
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "webapp" / "index.html"
FONTS = ROOT / "webapp" / "fonts"
# What the Mini App shows besides its own copy: every deck, the board, the
# Library and the compatibility test. The bot's translations are not here;
# the Mini App never shows them.
CONTENT = [
    ROOT / "data" / "questions.yaml",
    ROOT / "data" / "steps69_ru.yaml",
    *sorted((ROOT / "data" / "library").glob("*.yaml")),
]
FACE = re.compile(r"@font-face\s*\{([^}]*)\}")
PRELOAD = re.compile(r"<link\s+rel=\"preload\"([^>]*)>")
# The four faces weighed 129 KB as eight files; a budget keeps the Latin
# pages from creeping back in.
BUDGET = 72_000


def faces() -> list[dict[str, str]]:
    html = INDEX.read_text(encoding="utf-8")
    found = []
    for body in FACE.findall(html):
        family = re.search(r"font-family:\s*'([^']+)'", body)
        url = re.search(r"src:\s*url\('([^']+)'\)", body)
        weight = re.search(r"font-weight:\s*(\d+)", body)
        assert family and url and weight, body
        found.append(
            {"family": family[1], "url": url[1], "weight": weight[1], "body": body.strip()}
        )
    return found


@cache
def script() -> ModuleType:
    """scripts/fetch_webapp_fonts.py, which says what a face keeps."""
    spec = importlib.util.spec_from_file_location(
        "fetch_webapp_fonts", ROOT / "scripts" / "fetch_webapp_fonts.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def cmap(name: str) -> frozenset[int]:
    return frozenset(TTFont(FONTS / name).getBestCmap())


def drawn_by_the_brand(char: str) -> bool:
    """A character the brand faces are there to draw: a letter, a digit, a
    punctuation mark or a space, and anything from the Latin-1 page the
    face used to take whole. An arrow, a suit or an emoji is the phone's."""
    if char == "\u00a0":
        return True
    if not char.isprintable():
        return False
    return ord(char) < 0x100 or unicodedata.category(char)[0] in "LNP"


def text_the_app_sets() -> str:
    html = INDEX.read_text(encoding="utf-8")
    i18n = html.split("const I18N = {", 1)[1].split("\n  };", 1)[0]
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]
    content = "".join(path.read_text(encoding="utf-8") for path in CONTENT)
    # bindShortWords glues a short word to the next with a no-break space.
    return i18n + title + content + "\u00a0"


def test_a_face_is_one_file_and_every_file_a_face():
    found = faces()
    pairs = [(face["family"], face["weight"]) for face in found]
    assert sorted(pairs) == [("Inter", "400"), ("Inter", "600"), ("Inter", "700"), ("Lora", "400")]
    for face in found:
        # One file holds the whole face: a unicode-range would split it again.
        assert "unicode-range" not in face["body"], face["body"]
        assert (ROOT / "webapp" / face["url"]).is_file(), face["url"]
    shipped = {path.name for path in FONTS.iterdir()}
    assert shipped == {Path(face["url"]).name for face in found}, shipped


def test_each_face_is_preloaded_as_the_face_will_ask_for_it():
    """A preload that does not match the font's own request - another URL,
    or no crossorigin, since a font is always fetched in CORS mode - is a
    second download of the same file, and nothing but a console warning
    says so. Every face is on the first screen, so every face is preloaded;
    tests/e2e/browser/test_fonts.py counts the requests in both engines."""
    html = INDEX.read_text(encoding="utf-8")
    head = html.split("<style>", 1)[0]
    preloads = PRELOAD.findall(head)
    hrefs = []
    for attrs in preloads:
        assert 'as="font"' in attrs and 'type="font/woff2"' in attrs, attrs
        assert re.search(r"\scrossorigin(\s|$|=\"anonymous\")", attrs), attrs
        hrefs.append(re.search(r'href="([^"]+)"', attrs)[1])  # type: ignore[index]
    assert sorted(hrefs) == sorted(face["url"] for face in faces())


@pytest.mark.parametrize("name", sorted(p.name for p in FONTS.glob("*.woff2")))
def test_every_character_the_app_sets_is_in_the_face(name):
    needed = {char for char in text_the_app_sets() if drawn_by_the_brand(char)}
    missing = sorted(char for char in needed if ord(char) not in cmap(name))
    assert not missing, (
        f"{name} lacks {', '.join(f'U+{ord(c):04X} {c!r}' for c in missing)}: add them to "
        "TEXT in scripts/fetch_webapp_fonts.py and run it"
    )


@pytest.mark.parametrize("name", sorted(p.name for p in FONTS.glob("*.woff2")))
def test_a_face_holds_only_what_the_script_keeps(name):
    kept = script().TEXT | script().CYRILLIC
    extra = sorted(code for code in cmap(name) if code not in kept)
    assert not extra, f"{name} holds {', '.join(f'U+{c:04X}' for c in extra)}"
    # The punctuation of Russian typography, all of it.
    for char in "«»–…„“”№":
        assert ord(char) in cmap(name), (name, char)


def test_the_faces_stay_light():
    total = sum(path.stat().st_size for path in FONTS.glob("*.woff2"))
    assert total <= BUDGET, f"the web fonts weigh {total} B, over the {BUDGET} B budget"
