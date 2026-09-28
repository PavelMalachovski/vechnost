"""The brand fonts and generated cards must actually be in the repo.

They are binary assets no other test would notice missing: the renderer
silently falls back to DejaVu, and a missing background raises only at
render time, inside a try block.
"""

import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageFont

REPO_ROOT = Path(__file__).parent.parent
FONTS = REPO_ROOT / "assets" / "fonts"
WEBAPP_FONTS = REPO_ROOT / "webapp" / "fonts"
BACKGROUNDS = REPO_ROOT / "assets" / "backgrounds"
DECK_ART = REPO_ROOT / "assets" / "deck_art"
SUITS = REPO_ROOT / "assets" / "suits"
CARD_SIZE = (1080, 1350)
SUIT_NAMES = ["hearts", "spades", "clubs", "diamonds"]
FACES = sorted(path.relative_to(BACKGROUNDS).as_posix() for path in BACKGROUNDS.rglob("*.png"))
DECK_FACES = sorted(path.relative_to(DECK_ART).as_posix() for path in DECK_ART.rglob("*.png"))

# One representative letter per alphabet the cards actually set.
CYRILLIC = "Ж"
LATIN = "V"


@pytest.mark.parametrize(
    "name",
    [
        "Forum-Regular.ttf",
        "Lora-Regular.ttf",
        "Inter-Regular.ttf",
        "Inter-SemiBold.ttf",
    ],
)
def test_brand_font_is_present_and_loadable(name):
    path = FONTS / name
    assert path.exists(), f"missing font {name}"
    ImageFont.truetype(str(path), 48)


@pytest.mark.parametrize(
    "name",
    [
        "Forum-Regular.ttf",
        "Lora-Regular.ttf",
        "Inter-Regular.ttf",
    ],
)
def test_brand_font_covers_cyrillic(name):
    """Russian is the only language now — a latin-only subset would tofu."""
    font = ImageFont.truetype(str(FONTS / name), 48)
    notdef = bytes(font.getmask("￾"))
    assert bytes(font.getmask(CYRILLIC)) != notdef
    assert bytes(font.getmask(LATIN)) != notdef


@pytest.mark.parametrize(
    "name",
    [
        "lora-400.woff2",
        "inter-400.woff2",
        "inter-600.woff2",
        "inter-700.woff2",
    ],
)
def test_webapp_font_is_present(name):
    path = WEBAPP_FONTS / name
    assert path.exists(), f"missing webapp font {name}"
    assert path.stat().st_size > 1000, f"{name} looks like an error page"


@pytest.mark.parametrize("name", FACES)
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
    # The three Sex faces print the same V and club, so they are one picture.
    "acq/acq_1.png": "de0a84a94e80711c9a74faf60228847d14c3bdfcab8473d9a79013ccf7a3516a",
    "acq/acq_2.png": "3ad8e2ee3ba4bc24273c24e63bdd5e528d2cc18b5c5270be1f15be75e306b1bc",
    "acq/acq_3.png": "ce372938b560e6f407d6b6b5f5de076f55c395331e929ab7ba7ba317560db89e",
    "couples/couples_1.png": "aec08f0f91a1463f95656dce67b92573d11d262a0b2f72963b1ed6684c1be246",
    "couples/couples_2.png": "451a9ab1cf7c0f2d9d3b19717d56c42381db7d1ea9a55ce774351640360e8e75",
    "couples/couples_3.png": "3fc1699027fb267f1ff9f090a3472de3e55e8dd19f3c81fc5bcdd423d516f3b3",
    "prov/prov.png": "2d3468b4ce65ebcab65b10092bba9123149387f266d15129f86c45b86b6d229d",
    "sex/questions.png": "6078c467400127f73846db9b94f0beb89fbcf90c305d3707a1e76b32e89f7ae7",
    "sex/sex.png": "6078c467400127f73846db9b94f0beb89fbcf90c305d3707a1e76b32e89f7ae7",
    "sex/tasks.png": "6078c467400127f73846db9b94f0beb89fbcf90c305d3707a1e76b32e89f7ae7",
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


@pytest.mark.parametrize("name", sorted(CARD_SHA256))
def test_generated_card_is_the_art_the_generator_produces(name):
    digest = hashlib.sha256((BACKGROUNDS / name).read_bytes()).hexdigest()
    assert digest == CARD_SHA256[name], (
        f"{name} is not the committed art. If you meant to change it, regenerate and pin: {digest}"
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


def test_every_deck_face_is_generated_from_its_art():
    """A face with no art behind it could not be regenerated, and art with
    no face would be a deck the bot cannot print."""
    assert DECK_FACES, "no deck art in assets/deck_art"
    assert set(DECK_FACES) <= set(FACES)
    assert set(DECK_FACES) <= set(CARD_SHA256)


def _ink(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """The box of every pixel inside `box` that is not the card's bare ground."""
    crop = image.crop(box)
    bare = Image.new("RGB", crop.size, image.getpixel((5, 5)))
    mask = ImageChops.difference(crop, bare).convert("L").point(lambda v: 255 if v > 10 else 0)
    left, top, right, bottom = mask.getbbox()
    return (box[0] + left, box[1] + top, box[0] + right, box[1] + bottom)


def _ratio(box: tuple[int, int, int, int]) -> float:
    return (box[2] - box[0]) / (box[3] - box[1])


@pytest.mark.parametrize("face", DECK_FACES)
def test_a_deck_face_draws_each_mark_as_the_art_does(face):
    """Audit D-18. The art is 2:3 and the card 4:5, and the bot used to
    resize one into the other: every V, rank and suit came out a fifth wider
    than drawn. On the face each mark keeps the art's proportions, within a
    rasteriser's hair (the stretched ones were 18-24 % off), and its centre
    stays where that resize put it, which is what keeps CORNER_MARKS and the
    text layout where they were. The bottom-right pair is the top-left one
    turned round, as the art prints it."""
    with Image.open(DECK_ART / face) as art_image, Image.open(BACKGROUNDS / face) as card_image:
        art, card = art_image.convert("RGB"), card_image.convert("RGB")
    sx, sy = card.width / art.width, card.height / art.height
    for region in ((0, 0, 120, 127), (0, 127, 120, 200)):  # the rank, then the suit
        drawn = _ink(art, region)
        printed = _ink(
            card, tuple(round(v * s) for v, s in zip(region, (sx, sy, sx, sy), strict=True))
        )
        assert _ratio(printed) == pytest.approx(_ratio(drawn), rel=0.06), (face, drawn, printed)
        assert (printed[0] + printed[2]) / 2 == pytest.approx((drawn[0] + drawn[2]) / 2 * sx, abs=2)
        assert (printed[1] + printed[3]) / 2 == pytest.approx((drawn[1] + drawn[3]) / 2 * sy, abs=2)
    top_left = _ink(card, (0, 0, card.width // 2, card.height // 2))
    bottom_right = _ink(card, (card.width // 2, card.height // 2, card.width, card.height))
    turned = (
        card.width - bottom_right[2],
        card.height - bottom_right[3],
        card.width - bottom_right[0],
        card.height - bottom_right[1],
    )
    assert all(abs(a - b) <= 1 for a, b in zip(turned, top_left, strict=True)), (top_left, turned)
