"""Generate every card face the bot composites onto and the Mini App shows.

The deck faces — `acq/`, `couples/`, `sex/`, `prov/` — at the card's own
1080×1350, from the hand-drawn 600×900 art in `assets/deck_art/`.
`library.png` — the face every Library item and the daily prompt is set on.
`card_back.png` — the shared back the Mini App flips.
`suits/*.png` — the four emblems on their own, transparent, for anywhere a
suit has to be shown at a size the corner mark cannot survive: the Mini App's
home-screen fan renders them as an Ace's centre pip.

The suits are *cropped from the deck art* rather than redrawn: they are
shaded illustrations, not glyphs, and any redraw would drift from the cards
the bot already sends. Run this only when the art changes; the PNGs are
committed.

    python scripts/generate_card_assets.py
"""

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
BG = ROOT / "assets" / "backgrounds"
DECK_ART = ROOT / "assets" / "deck_art"
SUITS_DIR = ROOT / "assets" / "suits"
FONTS = ROOT / "assets" / "fonts"

CARD = (1080, 1350)

# Every colour below is sampled from the deck art so the new cards are cut
# from the same cloth as the ones the bot already sends.
PALE = (255, 229, 250)  # the deck's own ground
DARK = (74, 7, 58)  # the deck's own ink, used as a field
INK = (74, 7, 58)  # the V/Λ on the pale card
PALE_WATERMARK = (250, 214, 243)  # VECHNOST on the pale card: barely there
PINK = (254, 167, 236)  # the suit pink, reused for ink on the back

# Corner geometry, in the 1080×1350 frame. Derived from the deck cards, which
# are 600×900: there the V spans x 64-105 / y 76-125 and the emblem sits in
# x 60-109 centred on y 161. Scaled ×1.8 that is a 90px-wide emblem whose left
# edge is 108 from the card edge, under a V of 90px cap height.
MARGIN = 108
SUIT_W = 90  # nominal emblem width, matching the deck
CLUSTER_CX = MARGIN + SUIT_W // 2
LETTER_CAP = 90  # cap height of the V/Λ
GAP_BELOW_V = 65  # V cap bottom → emblem centre, per the deck

WORDMARK_CY = CARD[1] // 2  # cap-height centre of VECHNOST on the back
WORDMARK_W = 760  # how far the letter-spaced wordmark spans

# On the Library face the wordmark lay across the middle, right under every
# question of the day (audit D-36). It sits in the bottom third now, in the
# band no text reaches: the longest prompt ends above y=1045 and the footer
# starts at 1198 (renderer.FOOTER_BOTTOM_MARGIN), and the Mini App sets its
# text inside 327-1023 and its footer from 1177. Narrower than on the back,
# so its last letter clears the Λ in the corner (x from 882, y from 1152).
LIBRARY_WORDMARK_CY = 1110
LIBRARY_WORDMARK_W = 640
LIBRARY_WORDMARK_SIZE = 80

# Where the suit sits on each source card, as a fraction of that card's size.
# Measured, not guessed: scanning the four deck cards for pixels that differ
# from the flat ground puts every emblem inside x 60-109, y 132-192 (heart
# 60-109/139-179, spade 60-109/134-186, club 60-108/133-192, diamond
# 60-105/132-192). The box below is a 70×70 square centred on that cluster —
# square so one resize scales all four suits alike, and starting at y=127 so
# it clears the V above (which ends at y=125).
_SRC_SUIT = (49.5 / 600, 127 / 900, 119.5 / 600, 197 / 900)

# The crop is 70 source px wide and holds a 50px emblem, so a cell of this
# size renders the emblem at SUIT_W.
SUIT_BOX = round(SUIT_W * 70 / 50)

# Which deck card each suit is cut from. One mapping, because the back and the
# standalone emblems must show the same four marks; the deck's own suits are
# Acquaintance ♥, For Couples ♠, Sex ♣, Provocation ♦.
SUIT_SOURCES = {
    "hearts": "acq/acq_1.png",
    "spades": "couples/couples_1.png",
    "clubs": "sex/sex.png",
    "diamonds": "prov/prov.png",
}

# The deck faces, and the rank each carries above its suit. The art is 2:3
# and the card 4:5, so no single scale maps one onto the other: the bot used
# to resize the art into the card, ×1.8 across and ×1.5 down, and so printed
# every V, rank and suit a fifth wider than drawn (audit D-18). A face is now
# drawn at the card's size instead, each mark centred where that resize put
# it — so renderer.CORNER_MARKS and every card's text layout stay where they
# were — and scaled ×1.5 both ways, the height the resize already gave it.
DECK_FACES = {
    "acq/acq_1.png": "V",
    "acq/acq_2.png": "2",
    "acq/acq_3.png": "3",
    "couples/couples_1.png": "V",
    "couples/couples_2.png": "2",
    "couples/couples_3.png": "3",
    "prov/prov.png": "V",
    # One face for the Sex deck's questions and its tasks: the art was the
    # same picture three times over, under three names (audit D-42). A deck
    # that wants its own face gets its own art and its own line here.
    "sex/sex.png": "V",
}

_GROUND_TOL = 30  # channel-sum distance still counted as bare card
_FRINGE = 2  # px of source ring blended toward the pale ground
_BLEED = 2  # px of colour pushed past the mask, to feed the soft edge


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _centre_text(draw, xy, text, font, fill, tracking=0):
    """Draw text centred on xy, optionally letter-spaced.

    `xy` is the centre of the text's *cap box*, so callers can place a
    wordmark by where it looks centred rather than by font ascender.
    """
    x, y = xy
    top, bottom = font.getbbox(text)[1], font.getbbox(text)[3]
    y -= (top + bottom) / 2
    if not tracking:
        w = draw.textlength(text, font=font)
        draw.text((x - w / 2, y), text, font=font, fill=fill)
        return
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    cx = x - total / 2
    for ch, w in zip(text, widths, strict=True):
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += w + tracking


def _tracking_for(font, text, width) -> float:
    """The letter-spacing that makes `text` span exactly `width`."""
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    widths = [dummy.textlength(ch, font=font) for ch in text]
    return (width - sum(widths)) / (len(text) - 1)


def _letter(text: str, cap: int, fill, rotate: int = 0) -> Image.Image:
    """A single Forum letter as a tile trimmed to its ink, `cap` px tall.

    Forum has no Λ, and the deck's bottom-right mark is the top-left one
    turned around anyway — so the Λ is a V rotated 180°, exactly as printed.
    """
    probe = _font("Forum-Regular.ttf", 128)
    _, top, _, bottom = probe.getbbox(text)
    font = _font("Forum-Regular.ttf", round(128 * cap / (bottom - top)))
    left, top, right, bottom = font.getbbox(text)
    tile = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((-left, -top), text, font=font, fill=fill)
    return tile.rotate(rotate, expand=True) if rotate else tile


def _suit(source: str, size: int) -> Image.Image:
    """The suit emblem of a deck card, cut out and scaled, alpha preserved.

    The ground is dropped by flood-filling inward from the crop's border, not
    by a per-pixel colour test: the emblems are shaded, and their pale
    highlights sit as close to the card's pink as the ground does — a
    threshold would punch holes through the middle of the heart. The source's
    own outermost ring is a blend toward pale pink, and would rim the emblem
    with light on the dark back. Eroding it away is not the answer — that also
    strips the emblem's dark outline and leaves a glowing blob — so the
    silhouette is kept whole and only its *colour* is taken from further in.
    The mask is then resampled rather than thresholded, so the emblem lands
    with a smooth edge instead of a jagged one, and the ramp is steepened
    afterwards so "smooth" doesn't turn into "blurred".
    """
    with Image.open(DECK_ART / source) as img:
        card = img.convert("RGB")
    w, h = card.size
    ground = card.getpixel((5, 5))
    left, top, right, bottom = _SRC_SUIT
    box = card.crop((int(w * left), int(h * top), int(w * right), int(h * bottom)))
    bw, bh = box.size
    px = box.load()

    def far(x, y):
        c = px[x, y]
        return sum(abs(c[i] - ground[i]) for i in range(3)) > _GROUND_TOL

    # Everything the border can reach without crossing the emblem is ground.
    outside = bytearray(bw * bh)
    queue = deque()
    for x in range(bw):
        for y in (0, bh - 1):
            queue.append((x, y))
    for y in range(bh):
        for x in (0, bw - 1):
            queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < bw and 0 <= y < bh) or outside[y * bw + x] or far(x, y):
            continue
        outside[y * bw + x] = 1
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

    def is_out(x, y):
        return not (0 <= x < bw and 0 <= y < bh) or outside[y * bw + x]

    # `solid` is the emblem's silhouette; `core` is that silhouette minus the
    # blended ring the source antialiased against pale pink.
    solid = bytearray(bw * bh)
    for y in range(bh):
        for x in range(bw):
            solid[y * bw + x] = 0 if is_out(x, y) else 1
    core = bytearray(solid)
    for _ in range(_FRINGE):
        eroded = bytearray(core)
        for y in range(bh):
            for x in range(bw):
                if not core[y * bw + x]:
                    continue
                if any(
                    not core[(y + dy) * bw + x + dx]
                    if 0 <= x + dx < bw and 0 <= y + dy < bh
                    else True
                    for dy in (-1, 0, 1)
                    for dx in (-1, 0, 1)
                ):
                    eroded[y * bw + x] = 0
        core = eroded

    rgb = Image.new("RGB", box.size, ground)
    alpha = Image.new("L", box.size, 0)
    for y in range(bh):
        for x in range(bw):
            if solid[y * bw + x]:
                alpha.putpixel((x, y), 255)
            if core[y * bw + x]:
                rgb.putpixel((x, y), px[x, y])

    # Grow the core's colour outward over the ring and a little past the mask,
    # so both the silhouette's rim and the apron the resize samples carry
    # emblem colour instead of the pale pink the source blended into. It runs
    # until the whole silhouette is covered, not a fixed number of passes: a
    # thin spur like the diamond's tip or the spade's stem is narrower than
    # the ring, so it has no core of its own and would otherwise keep the
    # ground colour and flash white on the dark back.
    filled = bytearray(core)
    apron = 0
    while apron <= _BLEED:
        grown = bytearray(filled)
        for y in range(bh):
            for x in range(bw):
                if filled[y * bw + x]:
                    continue
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < bw and 0 <= ny < bh and filled[ny * bw + nx]:
                        rgb.putpixel((x, y), rgb.getpixel((nx, ny)))
                        grown[y * bw + x] = 1
                        break
        if grown == filled:
            break
        filled = grown
        if all(filled[i] or not solid[i] for i in range(bw * bh)):
            apron += 1

    rgb = rgb.resize((size, size), Image.Resampling.BICUBIC)
    alpha = alpha.resize((size, size), Image.Resampling.LANCZOS)
    # Squeeze the resampled ramp back to about a pixel: still graded, so the
    # edge reads smooth, but no longer a halo.
    alpha = alpha.point(lambda a: max(0, min(255, round((a - 96) * 255 / 64))))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def _ink_box(card: Image.Image, region: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Where the ink is inside `region` of a deck card: the box of every
    pixel that is not the card's bare ground."""
    ground = card.getpixel((5, 5))
    crop = card.crop(region)
    px = crop.load()
    hits = [
        (x, y)
        for y in range(crop.height)
        for x in range(crop.width)
        if sum(abs(px[x, y][i] - ground[i]) for i in range(3)) > _GROUND_TOL
    ]
    xs, ys = [x for x, _ in hits], [y for _, y in hits]
    return (
        region[0] + min(xs),
        region[1] + min(ys),
        region[0] + max(xs) + 1,
        region[1] + max(ys) + 1,
    )


def _paste_centred(card: Image.Image, tile: Image.Image, cx: int, cy: int):
    card.paste(tile, (round(cx - tile.width / 2), round(cy - tile.height / 2)), tile)


def _wordmark(card: Image.Image, size: int, fill, cy: float = WORDMARK_CY, width: int = WORDMARK_W):
    draw = ImageDraw.Draw(card)
    lora = _font("Lora-Regular.ttf", size)
    _centre_text(
        draw,
        (CARD[0] / 2, cy),
        "VECHNOST",
        lora,
        fill,
        tracking=_tracking_for(lora, "VECHNOST", width),
    )


def build_library_card() -> Image.Image:
    """Pale card: V top-left, Λ bottom-right, a whisper of VECHNOST in the
    bottom third, below where any text is set.

    It is also the renderer's fallback face (`default:` in
    assets/backgrounds.yml): neutral, and generated like every other face,
    where default.png was a leftover of the old design (audit D-43).
    """
    card = Image.new("RGB", CARD, PALE)
    _wordmark(
        card,
        LIBRARY_WORDMARK_SIZE,
        PALE_WATERMARK,
        cy=LIBRARY_WORDMARK_CY,
        width=LIBRARY_WORDMARK_W,
    )

    v = _letter("V", LETTER_CAP, INK)
    lam = _letter("V", LETTER_CAP, INK, rotate=180)
    _paste_centred(card, v, CLUSTER_CX, MARGIN + LETTER_CAP / 2)
    _paste_centred(card, lam, CARD[0] - CLUSTER_CX, CARD[1] - MARGIN - LETTER_CAP / 2)
    return card


def build_deck_face(source: str, rank: str) -> Image.Image:
    """One deck face at the card's size: the art's ground, its rank and suit
    redrawn in the top-left corner at their true proportions, and the pair
    turned round in the bottom-right, as the art prints them.

    The rank is set in Forum, the face it was drawn in, at the height the art
    gives it. The suit is this card's own, lifted with the ground around it
    and scaled as a square: the face has the same ground, so there is nothing
    to cut out, and the art's own antialiasing survives. (`_suit` cuts the
    emblem out for the dark back, and at this size its steepened edge reads
    as a staircase on pale.) Where each goes is read off the art rather than
    typed in, so a rank a pixel off on one card stays a pixel off.
    """
    with Image.open(DECK_ART / source) as img:
        art = img.convert("RGB")
    w, h = art.size
    sx, sy = CARD[0] / w, CARD[1] / h
    scale = sy

    left, top, right, bottom = _SRC_SUIT
    x0, y0, x1, y1 = _ink_box(art, (0, 0, round(w * right), round(h * top)))
    letter = _letter(rank, round((y1 - y0) * scale), INK)
    box = (int(w * left), int(h * top), int(w * right), int(h * bottom))
    patch = art.crop(box)
    suit = patch.resize(
        (round(patch.width * scale), round(patch.height * scale)), Image.Resampling.LANCZOS
    ).convert("RGBA")

    card = Image.new("RGB", CARD, art.getpixel((5, 5)))
    # The suit's square is opaque, so it goes down first and the rank over it.
    for tile, cx, cy in (
        (suit, (box[0] + box[2]) / 2 * sx, (box[1] + box[3]) / 2 * sy),
        (letter, (x0 + x1) / 2 * sx, (y0 + y1) / 2 * sy),
    ):
        _paste_centred(card, tile, cx, cy)
        _paste_centred(card, tile.transpose(Image.Transpose.ROTATE_180), CARD[0] - cx, CARD[1] - cy)
    return card


def build_card_back() -> Image.Image:
    """Dark back: all four suits in the corners, VECHNOST across the middle."""
    card = Image.new("RGB", CARD, DARK)
    _wordmark(card, 104, PINK)

    heart, spade, club, diamond = (
        _suit(SUIT_SOURCES[name], SUIT_BOX) for name in ("hearts", "spades", "clubs", "diamonds")
    )

    v = _letter("V", LETTER_CAP, PINK)
    lam = _letter("V", LETTER_CAP, PINK, rotate=180)

    right = CARD[0] - CLUSTER_CX
    suit_cy = MARGIN + LETTER_CAP + GAP_BELOW_V
    bottom_cy = CARD[1] - suit_cy

    _paste_centred(card, v, CLUSTER_CX, MARGIN + LETTER_CAP / 2)
    _paste_centred(card, heart, CLUSTER_CX, suit_cy)
    _paste_centred(card, club, right, suit_cy)
    _paste_centred(card, diamond, CLUSTER_CX, bottom_cy)
    _paste_centred(card, spade, right, bottom_cy)
    _paste_centred(card, lam, right, CARD[1] - MARGIN - LETTER_CAP / 2)
    return card


def build_suit_emblems() -> dict[str, Image.Image]:
    """Each suit alone on transparency, at the size the card back uses.

    Square tiles, all four cut from the same 70x70 box, so a caller that sizes
    one tile has sized all four alike – the heart and the club keep their own
    proportions inside it instead of being stretched to a common outline. The
    source emblem is 50px in the 600x900 deck art, so SUIT_BOX is as much
    resolution as there is; asking for a larger tile would only add blur.
    """
    return {name: _suit(source, SUIT_BOX) for name, source in SUIT_SOURCES.items()}


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog="Rewrites the deck faces in assets/backgrounds, library.png, "
        "card_back.png and assets/suits/*.png; commit them with the change "
        "that needed them.",
    ).parse_args()
    for source, rank in DECK_FACES.items():
        (BG / source).parent.mkdir(parents=True, exist_ok=True)
        build_deck_face(source, rank).save(BG / source)
    build_library_card().save(BG / "library.png")
    build_card_back().save(BG / "card_back.png")
    SUITS_DIR.mkdir(parents=True, exist_ok=True)
    emblems = build_suit_emblems()
    for name, tile in emblems.items():
        tile.save(SUITS_DIR / f"{name}.png")
    print(
        f"wrote {len(DECK_FACES)} deck faces, library.png, card_back.png and "
        + ", ".join(f"suits/{n}.png" for n in emblems)
    )


if __name__ == "__main__":
    main()
