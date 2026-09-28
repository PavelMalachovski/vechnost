"""Build the Mini App's web fonts: one woff2 per face, cut to what the app sets.

Google Fonts serves a family as a row of subsets, one @font-face per
unicode-range. The Mini App loaded two of them per face, the Cyrillic and
the Latin one, and the Latin one weighed three times the Cyrillic - Latin-1
letters, a page of punctuation and the alternates behind them - for a page
whose Latin is its digits, its punctuation and the name VECHNOST (audit
D-41). This takes both subsets of each face from Google, keeps the
characters in `CYRILLIC` and `TEXT` with the features a browser applies
unasked, and merges the two into one file: one request per face instead of
two, at a third of the weight. Every glyph, advance and kerning pair is
Google's own, cut from the subset the page used to load it from, so a line
of text is drawn exactly as it was.

Needs fontTools with WOFF2 support (fonttools and brotli, in the dev extra).
"""

from __future__ import annotations

import argparse
import io
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent.parent / "webapp" / "fonts"

# family query -> output stem. Forum, the face of the V/Λ marks, is the card
# generator's (assets/fonts/Forum-Regular.ttf): nothing on the page is set
# in it, and the page no longer declares it.
WANTED = {
    "Lora:wght@400": "lora-400",
    "Inter:wght@400": "inter-400",
    "Inter:wght@600": "inter-600",
    "Inter:wght@700": "inter-700",
}

# Google's Cyrillic block, whole: Russian, and the letters of a partner's
# name written in Ukrainian or Belarusian.
CYRILLIC = frozenset([0x0301, *range(0x0400, 0x0460), 0x0490, 0x0491, 0x04B0, 0x04B1, 0x2116])

# From the Latin block, what the app writes besides Cyrillic: printable
# ASCII (the digits, the punctuation, a name in Latin letters, VECHNOST)
# and the punctuation of Russian typography. An arrow, a suit or an emoji
# is left to the phone's own font, as it always was.
TEXT = frozenset(
    [
        *range(0x20, 0x7F),
        0x00A0,  # no-break space: bindShortWords glues short words with it
        0x00AB,  # «
        0x00AD,  # soft hyphen
        0x00B0,  # °
        0x00B7,  # ·
        0x00BB,  # »
        0x2010,  # hyphen
        0x2011,  # non-breaking hyphen
        0x2013,  # –
        0x2014,  # —
        0x2018,  # ‘
        0x2019,  # ’
        0x201C,  # “
        0x201D,  # ”
        0x201E,  # „
        0x2022,  # •
        0x2026,  # …
    ]
)

# fontTools keeps by default the features a browser applies unasked, and
# three it does not: the fractions, which the page never asks for (it has no
# font-variant and no font-feature-settings). `locl` is applied by
# language, and the page's is Russian, for which neither face has any: what
# they carry is Bulgarian, Serbian, Catalan and Turkish forms, which no
# line on this page can reach. All four would only be weight.
UNASKED = {"frac", "numr", "dnom", "locl"}

_BLOCK = re.compile(r"unicode-range:([^;]+);", re.S)
_FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
_URL = re.compile(r"url\((https://[^)]+\.woff2)\)")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        return bytes(r.read())


def _blocks(family: str) -> dict[str, str]:
    """The URLs of a face's Cyrillic and Latin subsets, by block."""
    css = _get(f"https://fonts.googleapis.com/css2?family={family}").decode()
    found = {}
    for face in _FACE.findall(css):
        ranges = _BLOCK.search(face)
        url = _URL.search(face)
        if not ranges or not url:
            continue
        text = ranges.group(1)
        if "U+0301" in text or "U+0400" in text:
            found["cyrillic"] = url.group(1)
        elif text.strip().startswith("U+0000"):
            found["latin"] = url.group(1)
    missing = {"cyrillic", "latin"} - found.keys()
    if missing:
        raise SystemExit(f"Google Fonts served {family} without its {', '.join(missing)} block")
    return found


def _share_drawings(font: TTFont) -> None:
    """Point every composite at the first glyph drawn the same way.

    The Cyrillic subset carries its own copies of the Latin letters its
    composites are built from (А is drawn as A, Ё as Е with a diaeresis),
    and the merger keeps both copies under two names. A composite only
    borrows a drawing, so pointing it at the Latin copy draws the same
    thing, and the last subset drops the copies nothing reaches any more.
    """
    from fontTools.pens.recordingPen import RecordingPen

    glyphs = font.getGlyphSet()
    glyf = font["glyf"]
    # Only a simple glyph stands for a drawing: a composite drawn the same
    # as its own component (a soft hyphen built from the hyphen) would
    # otherwise be pointed at itself.
    first: dict[tuple[str, int], str] = {}
    alias = {}
    for name in font.getGlyphOrder():
        if not glyf[name].isComposite():
            pen = RecordingPen()
            glyphs[name].draw(pen)
            alias[name] = first.setdefault((repr(pen.value), glyphs[name].width), name)
    for name in font.getGlyphOrder():
        if glyf[name].isComposite():
            for component in glyf[name].components:
                component.glyphName = alias.get(component.glyphName, component.glyphName)


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=f"Writes the woff2 files to {OUT.relative_to(OUT.parent.parent)}/.",
    ).parse_args()

    from fontTools import subset
    from fontTools.merge import Merger
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.layout_features = sorted(set(options.layout_features) - UNASKED)
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 14]  # 14: where the font's licence is
    options.notdef_outline = True
    options.glyph_names = True  # for the merger; the last subset drops them

    OUT.mkdir(parents=True, exist_ok=True)
    written = set()
    for family, stem in WANTED.items():
        blocks = _blocks(family)
        with tempfile.TemporaryDirectory() as tmp:
            parts = []
            dates = None
            # Latin first: the merged face takes its vertical metrics and its
            # names from the first part, and the Latin subset is the one the
            # page measured a line by (it holds the space).
            for block, keep in (("latin", TEXT), ("cyrillic", CYRILLIC)):
                font = TTFont(io.BytesIO(_get(blocks[block])), recalcTimestamp=False)
                font.flavor = None
                subsetter = subset.Subsetter(options)
                subsetter.populate(unicodes=keep)
                subsetter.subset(font)
                dates = dates or (font["head"].created, font["head"].modified)
                part = Path(tmp) / f"{block}.ttf"
                font.save(part)
                parts.append(str(part))
            merged = Merger().merge(parts)
        # The merger dates its font now; the source's own dates keep a
        # second run byte for byte the same as the first.
        merged["head"].created, merged["head"].modified = dates
        _share_drawings(merged)
        options.glyph_names = False
        final = subset.Subsetter(options)
        final.populate(unicodes=merged.getBestCmap().keys())
        final.subset(merged)
        options.glyph_names = True
        merged.flavor = "woff2"
        merged.recalcTimestamp = False
        path = OUT / f"{stem}.woff2"
        merged.save(path)
        written.add(path.name)
        print(f"{path.name}  {path.stat().st_size} B  {len(merged.getBestCmap())} characters")
    for stale in sorted(OUT.glob("*.woff2")):
        if stale.name not in written:
            stale.unlink()
            print(f"{stale.name}  removed")


if __name__ == "__main__":
    main()
