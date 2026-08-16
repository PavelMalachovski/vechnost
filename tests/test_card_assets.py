"""The brand fonts and generated cards must actually be in the repo.

They are binary assets no other test would notice missing: the renderer
silently falls back to DejaVu, and a missing background raises only at
render time, inside a try block.
"""

import hashlib
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


# scripts/generate_card_assets.py is byte-deterministic: no randomness, no
# timestamp, no system font lookup — it draws from the TTFs in assets/fonts and
# saves with Pillow's defaults, and re-running it reproduces these files
# exactly. So the whole card can be pinned, which is what this checks. A single
# pixel probe passed a swapped suit, a shifted corner mark or a moved wordmark;
# a hash does not.
#
# If one of these fails, the art moved. Regenerate with
# `python scripts/generate_card_assets.py`, look at the two PNGs, and if the
# change was intended paste the new digest in — the failure message prints it.
CARD_SHA256 = {
    "library.png": "d2825d21ac1bf4f3b630e2d3332a3fc2b9c3d80afd92de0ae4f26eee92d0291e",
    "card_back.png": "125e5d7ba10c74fd6444af60b9970271cc78862d81288aa10a573931388bbc12",
}


@pytest.mark.parametrize("name", ["library.png", "card_back.png"])
def test_generated_card_is_the_art_the_generator_produces(name):
    digest = hashlib.sha256((BACKGROUNDS / name).read_bytes()).hexdigest()
    assert digest == CARD_SHA256[name], (
        f"{name} is not the committed art. If you meant to change it, "
        f"regenerate and pin: {digest}"
    )
