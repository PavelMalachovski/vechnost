"""What the bot's card renderer promises, checked on the real fonts and art.

These used to live in a performance suite that timed each render against a
wall clock and failed whenever the machine was busy. The timings are gone;
what the renders were also checking is kept here.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image

from vechnost_bot import renderer

BACKGROUND = str(Path(__file__).parent.parent / "assets" / "backgrounds" / "acq" / "acq_1.png")
# Wrapped naively at the size it is set in, this question leaves «год?» alone
# on its last line.
LONELY_LAST_WORD = "Что тебя удивило в нас за последний год?"


def test_a_card_is_a_full_size_jpeg():
    """JPEG, not PNG: a photographic background triples the bytes as PNG,
    and a phone on a train pulls every one of them down."""
    payload = renderer.render_card(LONELY_LAST_WORD, BACKGROUND).getvalue()

    assert payload.startswith(b"\xff\xd8\xff"), "a card is a JPEG"
    assert len(payload) > 10_000
    with Image.open(BytesIO(payload)) as card:
        assert card.size == (renderer.CARD_WIDTH, renderer.CARD_HEIGHT)


def test_a_long_card_with_footer_and_watermark_renders():
    payload = renderer.render_card(
        "Расскажи о моменте, когда ты понял, что доверяешь мне полностью, "
        "и о том, что этому предшествовало, во всех подробностях, "
        "которые ты помнишь.",
        BACKGROUND,
        footer="Знакомство · 12/50",
        watermark="VECHNOST",
    ).getvalue()
    assert payload.startswith(b"\xff\xd8\xff")


def test_a_lonely_last_word_is_pulled_back_onto_the_line_before():
    font_path = renderer._pick_font_path(LONELY_LAST_WORD)
    font, lines = renderer._fit_text(
        LONELY_LAST_WORD, renderer.TEXT_AREA_WIDTH, renderer.TEXT_AREA_HEIGHT, font_path
    )
    naive = renderer._wrap_text(LONELY_LAST_WORD, font, renderer.TEXT_AREA_WIDTH)
    # The case this test exists for: without balancing, one short word.
    assert len(naive[-1].split()) == 1

    assert len(lines) == len(naive)
    assert len(lines[-1].split()) > 1
    assert " ".join(lines) == " ".join(naive)
