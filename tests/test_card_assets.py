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
SUITS = REPO_ROOT / "assets" / "suits"
CARD_SIZE = (1080, 1350)
SUIT_NAMES = ["hearts", "spades", "clubs", "diamonds"]

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

# The same pinning, for the four emblems on their own. These carry no text at
# all — the generator only crops and resamples the deck art to make them —
# which is why they can be pinned somewhere the two cards above cannot: a
# machine whose FreeType sets the VECHNOST wordmark a hair differently still
# cuts byte-identical suits.
SUIT_SHA256 = {
    "hearts": "b53273779e0474ec42bdee57ce805dd78c4c5fe833af5ef904396b247043fc3f",
    "spades": "3abe1239cd68fef9a078ca1b46834088a7447531862768b931b8e6b21613cebe",
    "clubs": "190bec99e71b4ee2484d21633ceaffe2d46ccc8fcd4521c9c94a860f87740b9b",
    "diamonds": "ef47f4b0a897a6a8e0ece925e4ded2a68c58b9973d549280e2adc92ea17ba6c3",
}


@pytest.mark.parametrize("name", ["library.png", "card_back.png"])
def test_generated_card_is_the_art_the_generator_produces(name):
    digest = hashlib.sha256((BACKGROUNDS / name).read_bytes()).hexdigest()
    assert digest == CARD_SHA256[name], (
        f"{name} is not the committed art. If you meant to change it, "
        f"regenerate and pin: {digest}"
    )


@pytest.mark.parametrize("name", SUIT_NAMES)
def test_suit_emblem_is_a_square_tile_with_a_cut_out_alpha(name):
    """The Mini App's home fan sets these as an Ace's centre pip.

    Square, because all four are cut from one box so a single background-size
    scales the set alike; RGBA with a real hole around the emblem, because the
    pip sits on the deck card's own ground and a baked-in background would
    show as a paler rectangle on it.
    """
    path = SUITS / f"{name}.png"
    assert path.exists(), f"missing emblem {name}.png"
    with Image.open(path) as img:
        assert img.mode == "RGBA", f"{name}.png is {img.mode}, not RGBA"
        assert img.size[0] == img.size[1], f"{name}.png is not square: {img.size}"
        alpha = img.getchannel("A")
        assert alpha.getextrema() == (0, 255), (
            f"{name}.png has no cut-out: alpha runs {alpha.getextrema()}"
        )
        # The emblem must not fill the tile, or the crop caught the card edge.
        assert img.getbbox()[2] - img.getbbox()[0] < img.size[0]


@pytest.mark.parametrize("name", SUIT_NAMES)
def test_suit_emblem_is_the_art_the_generator_produces(name):
    digest = hashlib.sha256((SUITS / f"{name}.png").read_bytes()).hexdigest()
    assert digest == SUIT_SHA256[name], (
        f"{name}.png is not the committed art. If you meant to change it, "
        f"regenerate and pin: {digest}"
    )
