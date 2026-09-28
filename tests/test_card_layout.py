"""No card's text runs over the suit marks in the corners (audit D-17).

The deck faces carry a V with its suit in the top-left corner and a Λ with
its suit in the bottom-right. The renderer keeps text in a central band
that never reaches them, and four long «Провокация» cards (341-416
characters) overflowed that band at the smallest size and ran over both
marks. A text that long now gets the card's height beside the marks, with
the lines that pass one narrowed to clear it.

Two things are held here: every text in the deck, laid out on its own face
with the footer the bot prints, stays clear of `CORNER_MARKS`; and those
boxes really do cover the marks on every face, so a redrawn background
that moves a mark fails here instead of quietly putting text on it.
"""

from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageChops

from vechnost_bot.i18n import Language
from vechnost_bot.library import question_of_the_day
from vechnost_bot.renderer import (
    CARD_HEIGHT,
    CARD_WIDTH,
    CORNER_MARKS,
    FOOTER_BOTTOM_MARGIN,
    TEXT_AREA_HEIGHT,
    TEXT_FOOTER_GAP,
    _fit_text,
    _line_height,
    _pick_font_path,
    get_background_path,
    layout_text,
)

ROOT = Path(__file__).resolve().parent.parent
TOPICS = {"Acquaintance": "acq", "For Couples": "couples", "Sex": "sex", "Provocation": "prov"}


def _deck() -> list[tuple[str, str]]:
    """(background, text) for every card the bot can deal."""
    data = yaml.safe_load((ROOT / "data" / "questions.yaml").read_text(encoding="utf-8"))
    cards = []
    for theme, body in data["themes"].items():
        topic = TOPICS[theme]
        for level, content in (body.get("levels") or {0: body}).items():
            for kind, category in (("questions", "q"), ("tasks", "t")):
                for text in content.get(kind) or []:
                    cards.append((get_background_path(topic, int(level), category), text))
    return cards


def _overlaps(box, mark) -> bool:
    left, top, right, bottom = box
    m_left, m_top, m_right, m_bottom = mark
    return left < m_right and right > m_left and top < m_bottom and bottom > m_top


DECK = _deck()


def test_the_deck_is_all_here():
    assert len(DECK) > 300


@pytest.mark.parametrize("has_footer", [True, False], ids=["footer", "bare"])
def test_no_card_runs_over_a_corner_mark(has_footer):
    offenders = []
    for background, text in DECK:
        layout = layout_text(text, _pick_font_path(text), has_footer=has_footer)
        for box in layout.line_boxes():
            if any(_overlaps(box, mark) for mark in CORNER_MARKS) or box[1] < 0:
                offenders.append((Path(background).name, text[:60], box))
                break
            if has_footer and box[3] > CARD_HEIGHT - FOOTER_BOTTOM_MARGIN - TEXT_FOOTER_GAP:
                offenders.append((Path(background).name, text[:60], "under the footer"))
                break
    assert offenders == []


def test_the_daily_prompts_clear_the_library_face_marks_too():
    for day in range(1, 367):
        text, _ = question_of_the_day(day, Language.RUSSIAN)
        layout = layout_text(text, _pick_font_path(text), has_footer=True)
        for box in layout.line_boxes():
            assert not any(_overlaps(box, mark) for mark in CORNER_MARKS), (day, text)


def test_a_card_that_fits_the_band_is_laid_out_as_it_always_was():
    """Nearly every card: the band, the largest size that fits, centred."""
    in_band = 0
    for _, text in DECK:
        font_path = _pick_font_path(text)
        font, lines = _fit_text(text, 820, TEXT_AREA_HEIGHT, font_path)
        height = len(lines) * _line_height(font)
        if height > TEXT_AREA_HEIGHT:
            continue
        in_band += 1
        layout = layout_text(text, font_path, has_footer=True)
        assert (layout.font.size, layout.lines) == (font.size, lines)
        assert layout.top == (CARD_HEIGHT - height) // 2
    assert in_band >= len(DECK) - 10


def test_the_long_provocations_now_clear_the_marks_at_a_readable_size():
    long_ones = [t for _, t in DECK if len(t) > 330]
    assert len(long_ones) >= 3
    for text in long_ones:
        layout = layout_text(text, _pick_font_path(text), has_footer=True)
        assert layout.font.size >= 36, text[:40]


FACES = sorted(
    p
    for p in (ROOT / "assets" / "backgrounds").rglob("*.png")
    if p.name not in {"card_back.png", "default.png"}
)


@pytest.mark.parametrize("face", FACES, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_mark_boxes_cover_the_marks_on_every_face(face):
    """Measured the way the renderer sees a face: scaled to the card."""
    image = (
        Image.open(face).convert("RGB").resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
    )
    paper = Image.new("RGB", image.size, image.getpixel((CARD_WIDTH // 2, CARD_HEIGHT // 2)))
    ink = ImageChops.difference(image, paper).convert("L").point(lambda v: 255 if v > 40 else 0)

    half_w, half_h = CARD_WIDTH // 2, CARD_HEIGHT // 2
    top_left = ink.crop((0, 0, half_w, half_h)).getbbox()
    bottom_right = ink.crop((half_w, half_h, CARD_WIDTH, CARD_HEIGHT)).getbbox()
    assert top_left and bottom_right, "a face with no corner marks?"
    bottom_right = (
        bottom_right[0] + half_w,
        bottom_right[1] + half_h,
        bottom_right[2] + half_w,
        bottom_right[3] + half_h,
    )

    for measured, box in zip((top_left, bottom_right), CORNER_MARKS, strict=True):
        left, top, right, bottom = measured
        b_left, b_top, b_right, b_bottom = box
        assert b_left <= left and b_top <= top and right <= b_right and bottom <= b_bottom, (
            f"{face.name}: marks at {measured} are outside CORNER_MARKS {box}"
        )
    # And nothing else is printed where text goes.
    assert ink.crop((0, 0, CARD_WIDTH, CARD_HEIGHT)).getbbox() is not None
    assert ink.crop((half_w, 0, CARD_WIDTH, half_h)).getbbox() is None, "a mark top-right"
    assert ink.crop((0, half_h, half_w, CARD_HEIGHT)).getbbox() is None, "a mark bottom-left"
