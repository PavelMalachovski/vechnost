"""The bot's cards, as it sends them, against committed reference pictures.

`renderer.py` composites a question onto each deck's face, and until now
nothing but a person looking at a photo in the chat would notice that go
wrong: a size step lost, a colour drifted, a footer gone, lines run into
the corner marks. Here a card per deck face is rendered the way the bot
renders it, footer and watermark included, and compared with
`tests/references/cards/`.

The comparison is tolerant on purpose. The fonts ship in `assets/fonts`,
but the FreeType inside Pillow is not the same everywhere: CLAUDE.md notes
that a regenerated `card_back.png` sets its wordmark a hair differently on
another machine. So a card is compared at a quarter of its size, and what
has to match is what a reader would notice, not how each glyph is
anti-aliased:

* the picture as a whole (mean difference per channel at most `MEAN`, and
  at most `STRONG_PIXELS` pixels different by more than `STRONG`);
* where the ink is - the text block, the footer, the watermark - each
  band's bounding box within `BOX` pixels of the reference's, so a line,
  a footer or a watermark that moves, appears or goes is caught;
* the colour of each band's ink, within `COLOUR` per channel.

`test_the_comparison_forgives_a_hair_but_not_a_change` shows the line it
draws: every glyph moved by a whole pixel passes; one more word, a footer
20 px higher, a missing watermark or footer, the text or footer colour
drifted, all fail.

And on the pixels this time rather than on the layout, no text may touch a
corner mark (audit D-17; `test_card_layout.py` holds the layout for every
card in the decks): the ink is what differs between the card and its bare
face, and none of it may fall inside `CORNER_MARKS`.

A deliberate change to the cards: `UPDATE_CARD_REFERENCES=1 pytest
tests/test_card_references.py` writes new references, which a pull request
then shows as pictures.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

import vechnost_bot.renderer as renderer
from vechnost_bot.renderer import CARD_HEIGHT, CARD_WIDTH, CORNER_MARKS, render_card

ROOT = Path(__file__).resolve().parent.parent
REFERENCES = Path(__file__).parent / "references" / "cards"
UPDATE = os.environ.get("UPDATE_CARD_REFERENCES") == "1"
WATERMARK = "VECHNOST · @vechnost_bot"

SCALE = 4  # compared at a quarter of 1080x1350
MEAN = 5.0  # mean difference per channel, of 255
STRONG = 96  # a pixel this different is a different pixel...
STRONG_PIXELS = 40  # ...and this many of them are a different card
BOX = 2  # a band's ink may move this many (quarter) pixels
COLOUR = 12  # a band's ink colour may drift this much per channel
INK = 40  # at a quarter: what differs from the bare face by more is ink
FULL_INK = 60  # at full size, where JPEG ringing around the marks stays under it

W, H = CARD_WIDTH // SCALE, CARD_HEIGHT // SCALE
# The bands the ink falls in, top to bottom, at a quarter of the size.
_FOOTER_TOP = (CARD_HEIGHT - renderer.FOOTER_BOTTOM_MARGIN - 12) // SCALE
_WATERMARK_TOP = (CARD_HEIGHT - renderer.WATERMARK_BOTTOM_MARGIN - 8) // SCALE
BANDS = {
    "text": (0, 0, W, _FOOTER_TOP),
    "footer": (0, _FOOTER_TOP, W, _WATERMARK_TOP),
    "watermark": (0, _WATERMARK_TOP, W, H),
}

SHORT = "Какое твоё самое значимое воспоминание в жизни? Почему?"
MEDIUM = (
    "Что ты думаешь о том, чтобы жить вместе? Какие привычки друг друга "
    "нам придётся принять, а о каких стоит договориться заранее?"
)
LONG = (
    "Твой партнёр полностью обеспечивает тебя, у вас нет никаких "
    "финансовых проблем. Но однажды ты узнаёшь, что всё это время партнёр "
    "скрывал от тебя, откуда на самом деле берутся деньги: это работа, "
    "которую ты считаешь недопустимой. Партнёр обещает, что скоро всё "
    "изменится, но просит ничего не менять в вашей жизни. Твои действия? "
    "Останешься ли ты рядом и что скажешь в первый же вечер?"
)

# One card per deck face, and the Library's: (reference, face, footer,
# text). The texts are fixed rather than read from the decks, so editing a
# question never moves a reference. Between them they take the band at its
# largest size, a middling one, and a text too long for the band, laid out
# beside the marks. The Sex deck's questions and tasks share one face (audit
# D-42) and keep a card each; the Library card holds its wordmark below the
# text (D-36).
CARDS = [
    ("acq-1", "assets/backgrounds/acq/acq_1.png", "Знакомство · 1/30", SHORT),
    ("acq-2", "assets/backgrounds/acq/acq_2.png", "Знакомство · 7/30", MEDIUM),
    ("acq-3", "assets/backgrounds/acq/acq_3.png", "Знакомство · 12/33", LONG),
    ("couples-1", "assets/backgrounds/couples/couples_1.png", "Для пар · 1/30", MEDIUM),
    ("couples-2", "assets/backgrounds/couples/couples_2.png", "Для пар · 9/30", SHORT),
    ("couples-3", "assets/backgrounds/couples/couples_3.png", "Для пар · 30/30", LONG),
    ("sex-questions", "assets/backgrounds/sex/sex.png", "Секс · 3/93", MEDIUM),
    ("sex-tasks", "assets/backgrounds/sex/sex.png", "Секс · 4/93", SHORT),
    ("prov", "assets/backgrounds/prov/prov.png", "Провокация · 4/34", LONG),
    ("daily", "assets/backgrounds/library.png", "Вопрос дня · 271/365", MEDIUM),
]
IDS = [card[0] for card in CARDS]


def render(
    face: str, footer: str | None, text: str, watermark: str | None = WATERMARK
) -> Image.Image:
    data = render_card(text, str(ROOT / face), footer=footer, watermark=watermark)
    return Image.open(BytesIO(data.getvalue())).convert("RGB")


def bare(face: str) -> Image.Image:
    """The face as the renderer uses it, before any text."""
    image = Image.open(ROOT / face).convert("RGB")
    return image.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)


def small(image: Image.Image) -> Image.Image:
    return image.resize((W, H), Image.Resampling.LANCZOS)


@dataclass
class Look:
    """What a reader would notice of a card, at a quarter of its size."""

    boxes: dict[str, tuple[int, int, int, int] | None]
    colours: dict[str, tuple[float, ...] | None]


def look(card: Image.Image, face: str) -> Look:
    ink = ImageChops.difference(card, small(bare(face))).convert("L")
    ink = ink.point(lambda v: 255 if v > INK else 0)
    boxes: dict[str, tuple[int, int, int, int] | None] = {}
    colours: dict[str, tuple[float, ...] | None] = {}
    for band, area in BANDS.items():
        mask = Image.new("L", card.size)
        mask.paste(ink.crop(area), area[:2])
        boxes[band] = mask.getbbox()
        colours[band] = tuple(ImageStat.Stat(card, mask=mask).mean) if boxes[band] else None
    return Look(boxes, colours)


def differences(reference: Image.Image, card: Image.Image, face: str) -> list[str]:
    """What a reader would notice between two cards at a quarter size; [] if nothing."""
    found = []
    diff = ImageChops.difference(reference, card)
    mean = sum(ImageStat.Stat(diff).mean) / 3
    strong = sum(diff.convert("L").histogram()[STRONG + 1 :])
    if mean > MEAN:
        found.append(f"mean difference {mean:.2f} (at most {MEAN})")
    if strong > STRONG_PIXELS:
        found.append(f"{strong} pixels different by more than {STRONG} (at most {STRONG_PIXELS})")
    was, now = look(reference, face), look(card, face)
    for band in BANDS:
        before, after = was.boxes[band], now.boxes[band]
        if (before is None) != (after is None):
            found.append(f"the {band} {'is gone' if after is None else 'appeared'}")
            continue
        if before and after and max(abs(a - b) for a, b in zip(before, after, strict=True)) > BOX:
            found.append(f"the {band} moved: {before} -> {after} (quarter-size pixels)")
        c0, c1 = was.colours[band], now.colours[band]
        if c0 and c1 and max(abs(a - b) for a, b in zip(c0, c1, strict=True)) > COLOUR:
            found.append(
                f"the {band}'s colour drifted: {tuple(round(v) for v in c0)} -> "
                f"{tuple(round(v) for v in c1)}"
            )
    return found


@pytest.mark.parametrize("name,face,footer,text", CARDS, ids=IDS)
def test_the_card_looks_as_its_reference(name: str, face: str, footer: str, text: str) -> None:
    card = small(render(face, footer, text))
    reference = REFERENCES / f"{name}.png"
    if UPDATE:
        reference.parent.mkdir(parents=True, exist_ok=True)
        card.save(reference, optimize=True)
    assert reference.exists(), (
        f"no reference: UPDATE_CARD_REFERENCES=1 pytest {Path(__file__).name}"
    )
    found = differences(Image.open(reference).convert("RGB"), card, face)
    assert not found, (
        f"{name} no longer looks like tests/references/cards/{name}.png: "
        + "; ".join(found)
        + ". If that is meant, UPDATE_CARD_REFERENCES=1 and let the pull request show the pictures."
    )


# How far JPEG rings past a corner mark: one 8x8 block.
_RINGING = 8


def _glyphs_moved(card: Image.Image, face: str, dx: int, dy: int) -> Image.Image:
    """The card with every glyph a whole pixel away: more than any rasteriser differs.

    A glyph is what the renderer drew, so what differs around the face's own
    corner marks is not one: the card is a JPEG and the face is not, and the
    ringing JPEG leaves around a crisp mark would otherwise travel with the
    text (a Λ's, moved down a pixel, lands in the watermark's band). No
    renderer ink comes near a mark; `test_no_ink_falls_on_a_corner_mark`
    holds that.
    """
    face_image = bare(face)
    ink = ImageChops.difference(card, face_image).convert("L").point(lambda v: 255 if v > 8 else 0)
    for left, top, right, bottom in CORNER_MARKS:
        ImageDraw.Draw(ink).rectangle(
            (left - _RINGING, top - _RINGING, right + _RINGING, bottom + _RINGING), fill=0
        )
    moved, moved_ink = Image.new("RGB", card.size), Image.new("L", card.size)
    moved.paste(card, (dx, dy))
    moved_ink.paste(ink, (dx, dy))
    out = face_image.copy()
    out.paste(moved, (0, 0), moved_ink)
    return out


@pytest.mark.parametrize(
    "name,face,footer,text", [CARDS[0], CARDS[3], CARDS[-1]], ids=IDS[:1] + IDS[3:4] + IDS[-1:]
)
def test_the_comparison_forgives_a_hair_but_not_a_change(
    name: str, face: str, footer: str, text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = render(face, footer, text)
    reference = small(card)
    for dx, dy in ((1, 0), (0, 1)):
        assert not differences(reference, small(_glyphs_moved(card, face, dx, dy)), face), (dx, dy)

    changes = {
        "one more word": lambda: render(face, footer, text + " Почему?"),
        "no watermark": lambda: render(face, footer, text, watermark=None),
        "no footer": lambda: render(face, None, text),
    }
    for label, make in changes.items():
        assert differences(reference, small(make()), face), label
    for label, attribute, value in (
        ("the footer 20 px higher", "FOOTER_BOTTOM_MARGIN", renderer.FOOTER_BOTTOM_MARGIN + 20),
        ("the text colour drifted", "TEXT_COLOR", (90, 20, 70)),
        ("the footer colour drifted", "FOOTER_COLOR", (170, 110, 150)),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(renderer, attribute, value)
            assert differences(reference, small(render(face, footer, text)), face), label


@pytest.mark.parametrize("name,face,footer,text", CARDS, ids=IDS)
def test_no_ink_falls_on_a_corner_mark(name: str, face: str, footer: str, text: str) -> None:
    card = render(face, footer, text)
    ink = (
        ImageChops.difference(card, bare(face))
        .convert("L")
        .point(lambda v: 255 if v > FULL_INK else 0)
    )
    assert ink.getbbox() is not None, "no text found at all, so this would prove nothing"
    for box in CORNER_MARKS:
        touched = ink.crop(box).getbbox()
        assert touched is None, f"{name}: text inside the corner mark at {box} ({touched})"
