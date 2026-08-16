"""The brand fonts and generated cards must actually be in the repo.

They are binary assets no other test would notice missing: the renderer
silently falls back to DejaVu, and a missing background raises only at
render time, inside a try block.
"""

from pathlib import Path

import pytest
from PIL import Image, ImageFont

REPO_ROOT = Path(__file__).parent.parent
FONTS = REPO_ROOT / "assets" / "fonts"
WEBAPP_FONTS = REPO_ROOT / "webapp" / "fonts"
BACKGROUNDS = REPO_ROOT / "assets" / "backgrounds"
CARD_SIZE = (1080, 1350)

# One representative letter per alphabet the cards actually set.
CYRILLIC = "Ж"
LATIN = "V"


@pytest.mark.parametrize("name", [
    "Forum-Regular.ttf", "Lora-Regular.ttf",
    "Inter-Regular.ttf", "Inter-SemiBold.ttf",
])
def test_brand_font_is_present_and_loadable(name):
    path = FONTS / name
    assert path.exists(), f"missing font {name}"
    ImageFont.truetype(str(path), 48)


@pytest.mark.parametrize("name", [
    "Forum-Regular.ttf", "Lora-Regular.ttf", "Inter-Regular.ttf",
])
def test_brand_font_covers_cyrillic(name):
    """Russian is the only language now — a latin-only subset would tofu."""
    font = ImageFont.truetype(str(FONTS / name), 48)
    notdef = bytes(font.getmask("￾"))
    assert bytes(font.getmask(CYRILLIC)) != notdef
    assert bytes(font.getmask(LATIN)) != notdef


@pytest.mark.parametrize("name", [
    "forum-400.woff2", "lora-400.woff2",
    "inter-400.woff2", "inter-600.woff2", "inter-700.woff2",
])
def test_webapp_font_is_present(name):
    path = WEBAPP_FONTS / name
    assert path.exists(), f"missing webapp font {name}"
    assert path.stat().st_size > 1000, f"{name} looks like an error page"


@pytest.mark.parametrize("name", ["library.png", "card_back.png"])
def test_generated_card_has_the_deck_geometry(name):
    """Every card the renderer composites onto must already be card-shaped;
    _load_background_image would otherwise resample it and soften the art."""
    path = BACKGROUNDS / name
    assert path.exists(), f"missing card {name}"
    with Image.open(path) as img:
        assert img.size == CARD_SIZE


def test_library_card_is_pale_and_back_is_dark():
    """The two cards carry opposite ink: text on the library card is dark on
    pale, the back is a solid dark field. A swapped file would be invisible."""
    with Image.open(BACKGROUNDS / "library.png") as img:
        r, g, b = img.convert("RGB").getpixel((540, 340))
        assert min(r, g, b) > 200
    with Image.open(BACKGROUNDS / "card_back.png") as img:
        r, g, b = img.convert("RGB").getpixel((540, 340))
        assert max(r, g, b) < 120
