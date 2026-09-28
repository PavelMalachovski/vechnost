"""Image rendering module for Vechnost bot cards."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .monitoring import log_image_rendering_event, track_performance

logger = logging.getLogger(__name__)

# Card geometry
CARD_WIDTH = 1080
CARD_HEIGHT = 1350
JPEG_QUALITY = 92

# Text block geometry.
# The card backgrounds have suit marks in the top-left and bottom-right corners,
# so the text lives in a central column that never touches them.
TEXT_AREA_WIDTH = int(CARD_WIDTH * 0.76)  # comfortable measure, ~30-38 chars/line
TEXT_AREA_HEIGHT = int(CARD_HEIGHT * 0.56)  # central band clear of corner marks

# Where the corner marks sit on the deck faces once scaled to the card: the
# top-left V with its suit and the bottom-right Λ with its suit, measured on
# every face in assets/backgrounds and given a few pixels of air, as
# (left, top, right, bottom). The central band above never reaches them. A
# text too long for the band uses the height beside them instead, with the
# lines that pass a mark narrowed to clear it (audit D-17: four long
# «Провокация» cards ran over the suits). tests/test_card_layout.py holds
# every card in the deck clear of these boxes, and the boxes over every face.
CORNER_MARKS = ((102, 108, 204, 295), (876, 1055, 978, 1242))
# Space kept between a line and a mark it passes beside.
CORNER_CLEARANCE = 10
# How high a long text may start: level with the top of the marks.
TEXT_TOP_LIMIT = 108

# Typography
MAX_FONT_SIZE = 84
MIN_FONT_SIZE = 44
# The floor for the few texts too long for the central band even at
# MIN_FONT_SIZE: still about 13 pt on a phone, which beats a line on a suit.
LONG_TEXT_MIN_FONT_SIZE = 36
LINE_SPACING = 1.32  # multiple of (ascent + descent)
TEXT_COLOR = (53, 0, 39)  # dark maroon #350027, ~13:1 contrast on the pale pink
FOOTER_COLOR = (122, 63, 100)  # muted plum, readable but secondary
FOOTER_FONT_SIZE = 30
# The Library card (library.png, used by the daily push) carries its Λ letter
# in the bottom-right corner, so the footer and watermark both stay above it.
# The deck backgrounds have their own corner marks at the same height; there
# the clearance simply reads as bottom padding.
FOOTER_BOTTOM_MARGIN = 152

# Brand watermark: quieter than the footer, one line below it.
WATERMARK_COLOR = (168, 118, 148)
WATERMARK_FONT_SIZE = 24
WATERMARK_BOTTOM_MARGIN = 107

# Minimum breathing room between the question text and the footer. The text
# block is centred on the card, but a card whose text overflows its area slides
# up rather than running into the footer.
TEXT_FOOTER_GAP = 14

# The only fonts this module draws with. Inter sets every card's text and
# covers Cyrillic; DejaVu is the last resort, and _pick_font_path picks between
# them per string, so a text in an alphabet Inter lacks (Greek, say) degrades
# instead of tofuing.
#
# The brand's other two faces are not the renderer's business. Lora (the
# VECHNOST wordmark) and Forum (the V/Λ letters and the 2/3 ranks) are printed
# *into* the backgrounds by scripts/generate_card_assets.py, which loads them
# by filename itself; renderer.py only composites question text onto the
# finished art. Look there, not here, if a wordmark or a rank looks wrong.
_ASSETS_FONTS = Path(__file__).parent.parent / "assets" / "fonts"
FONT_PATH = _ASSETS_FONTS / "Inter-Regular.ttf"
FALLBACK_FONT_PATH = _ASSETS_FONTS / "DejaVuSans.ttf"


@lru_cache(maxsize=32)
def _load_background_image(bg_path: str) -> Image.Image | None:
    """Load and cache background image."""
    try:
        path = Path(bg_path)
        if not path.exists():
            logger.warning(f"Background image not found: {bg_path}")
            return None

        image = Image.open(path)
        # Convert to RGB if necessary (for JPEG output)
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize to target dimensions if needed
        if image.size != (CARD_WIDTH, CARD_HEIGHT):
            image = image.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)

        return image
    except Exception as e:
        logger.error(f"Error loading background image {bg_path}: {e}")
        return None


@lru_cache(maxsize=8)
def _notdef_mask(font_path: str) -> bytes:
    """Bitmap of the font's .notdef (tofu) glyph, for coverage checks."""
    font = ImageFont.truetype(font_path, 48)
    return bytes(font.getmask("￾"))


@lru_cache(maxsize=4096)
def _char_covered(font_path: str, char: str) -> bool:
    """True if the font has a real glyph for char (not the tofu box)."""
    try:
        font = ImageFont.truetype(font_path, 48)
        return bytes(font.getmask(char)) != _notdef_mask(font_path)
    except Exception:
        return False


def _pick_font_path(text: str) -> str | None:
    """First bundled font that covers every letter of the text."""
    letters = {ch for ch in text if ch.isalpha()}
    for font_path in (FONT_PATH, FALLBACK_FONT_PATH):
        if not font_path.exists():
            continue
        if all(_char_covered(str(font_path), ch) for ch in letters):
            return str(font_path)

    # Try system fonts that support Cyrillic characters
    system_fonts = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for font_name in system_fonts:
        try:
            ImageFont.truetype(font_name, 48)
            return font_name
        except Exception:
            continue
    return None


@lru_cache(maxsize=128)
def _load_font(size: int, font_path: str | None = None) -> ImageFont.FreeTypeFont | None:
    """Load and cache font at specific size."""
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.warning(f"Could not load font {font_path}: {e}")

    for fallback in (FALLBACK_FONT_PATH, FONT_PATH):
        try:
            if fallback.exists():
                return ImageFont.truetype(str(fallback), size)
        except Exception:
            continue

    logger.warning(f"Font file not found: {FONT_PATH}, using default font")
    return ImageFont.load_default()


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> float:
    """Width of a single line of text in pixels."""
    return font.getlength(text)


def _break_long_word(word: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Split a single overlong word into hyphenated chunks that fit max_width."""
    chunks = []
    current = ""
    for char in word:
        candidate = current + char
        if _text_width(candidate + "-", font) <= max_width or not current:
            current = candidate
        else:
            chunks.append(current + "-")
            current = char
    if current:
        chunks.append(current)
    return chunks


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width, breaking overlong words with hyphens."""
    return _wrap_lines(text, font, lambda _line: max_width)


def _wrap_lines(
    text: str, font: ImageFont.FreeTypeFont, width_of: Callable[[int], int]
) -> list[str]:
    """Wrap text with a width per line (`width_of(line index)`), breaking
    overlong words with hyphens. The same greedy wrap as always; a line that
    passes a corner mark simply gets less room."""
    lines: list[str] = []
    current_line: list[str] = []

    for word in text.split():
        max_width = width_of(len(lines))
        if _text_width(word, font) > max_width:
            # Flush the current line, then split the long word across lines
            if current_line:
                lines.append(" ".join(current_line))
                current_line = []
            pieces = _break_long_word(word, font, width_of(len(lines)))
            lines.extend(pieces[:-1])
            current_line = [pieces[-1]]
            continue

        test_line = " ".join(current_line + [word])
        if _text_width(test_line, font) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def _balance_last_line(
    text: str, font: ImageFont.FreeTypeFont, max_width: int, lines: list[str]
) -> list[str]:
    """Avoid a lonely short word on the last line by re-wrapping slightly narrower."""
    if len(lines) < 2:
        return lines
    last = lines[-1]
    if len(last.split()) > 1 or _text_width(last, font) > max_width * 0.28:
        return lines

    for factor in (0.94, 0.88, 0.82):
        rewrapped = _wrap_text(text, font, int(max_width * factor))
        if len(rewrapped) == len(lines) and len(rewrapped[-1].split()) > 1:
            return rewrapped
    return lines


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    """Uniform line height from font metrics (ascent + descent), not per-line ink."""
    ascent, descent = font.getmetrics()
    return int((ascent + descent) * LINE_SPACING)


def _fit_text(
    text: str, max_width: int, max_height: int, font_path: str | None, single_line: bool = False
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """
    Pick the largest font size (MIN..MAX) whose wrapped text fits the area.

    Long questions shrink to fit; short ones render large and confident.
    With single_line, shrink until the text fits unbroken on one line —
    used for codes, where a wrap-inserted hyphen would read as content.
    """
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -4):
        font = _load_font(size, font_path)
        if not font:
            continue
        if single_line:
            if _text_width(text, font) <= max_width:
                return font, [text]
            continue
        lines = _wrap_text(text, font, max_width)
        if len(lines) * _line_height(font) <= max_height:
            lines = _balance_last_line(text, font, max_width, lines)
            return font, lines

    # Minimum size still overflows: keep it readable and let it run tall
    font = _load_font(MIN_FONT_SIZE, font_path)
    lines = _wrap_text(text, font, max_width)
    return font, lines


@dataclass(frozen=True)
class TextLayout:
    """Where a card's text goes: its font, its lines, the first line's top."""

    font: ImageFont.FreeTypeFont
    lines: list[str]
    top: int
    line_height: int

    def line_boxes(self) -> list[tuple[float, float, float, float]]:
        """Each line as drawn, centred: (left, top, right, bottom), where
        top and bottom are the font's ascent and descent, not the spacing."""
        ascent, descent = self.font.getmetrics()
        boxes = []
        for i, line in enumerate(self.lines):
            width = _text_width(line, self.font)
            left = (CARD_WIDTH - width) / 2
            y = self.top + i * self.line_height
            boxes.append((left, y, left + width, y + ascent + descent))
        return boxes


def _text_floor(has_footer: bool) -> int:
    """The lowest a line may reach: above the footer when there is one."""
    if has_footer:
        return CARD_HEIGHT - FOOTER_BOTTOM_MARGIN - TEXT_FOOTER_GAP
    return CARD_HEIGHT - TEXT_TOP_LIMIT


def _centred_top(total_height: int, has_footer: bool) -> int:
    """Centre the block on the card, but never under the footer."""
    top = (CARD_HEIGHT - total_height) // 2
    if has_footer:
        top = max(0, min(top, _text_floor(True) - total_height))
    return top


def _width_beside_marks(top: float, bottom: float) -> int:
    """How wide a centred line spanning [top, bottom) may be."""
    width = TEXT_AREA_WIDTH
    (tl_left, tl_top, tl_right, tl_bottom), (br_left, br_top, br_right, br_bottom) = CORNER_MARKS
    centre = CARD_WIDTH / 2
    if top < tl_bottom and bottom > tl_top:
        width = min(width, int(2 * (centre - tl_right - CORNER_CLEARANCE)))
    if top < br_bottom and bottom > br_top:
        width = min(width, int(2 * (br_left - CORNER_CLEARANCE - centre)))
    return width


def _around_the_marks(
    text: str, font: ImageFont.FreeTypeFont, has_footer: bool
) -> TextLayout | None:
    """The card's full height, lines beside a corner mark narrowed to
    clear it; None when the text does not fit even so.

    Where the lines fall depends on how many there are (the block is
    centred), and how many there are on how wide the lines beside the marks
    may be, so each line count is tried in turn until one is consistent:
    wrapped at the widths its own positions allow, and still that many
    lines.
    """
    line_height = _line_height(font)
    ascent, descent = font.getmetrics()
    ink = ascent + descent
    first = len(_wrap_text(text, font, TEXT_AREA_WIDTH))
    for count in range(first, first + 8):
        top = _centred_top(count * line_height, has_footer)

        def width_of(i: int, _top: int = top) -> int:
            y = _top + i * line_height
            return _width_beside_marks(y, y + ink)

        lines = _wrap_lines(text, font, width_of)
        if len(lines) > count:
            continue
        layout = TextLayout(
            font, lines, _centred_top(len(lines) * line_height, has_footer), line_height
        )
        boxes = layout.line_boxes()
        if boxes[0][1] < TEXT_TOP_LIMIT or boxes[-1][3] > _text_floor(has_footer):
            return None
        # Fewer lines than planned moves the block; it must still clear.
        if all(right - left <= _width_beside_marks(y0, y1) + 0.5 for left, y0, right, y1 in boxes):
            return layout
    return None


def layout_text(
    text: str, font_path: str | None, *, has_footer: bool, single_line: bool = False
) -> TextLayout:
    """Where `render_card` puts `text`.

    The central band first, at the largest size that fits, exactly as
    before: nearly every card is laid out here and looks as it always did.
    A text too long for the band at MIN_FONT_SIZE gets the card's height
    beside the corner marks, down to LONG_TEXT_MIN_FONT_SIZE, rather than
    running tall over them.
    """
    font, lines = _fit_text(
        text, TEXT_AREA_WIDTH, TEXT_AREA_HEIGHT, font_path, single_line=single_line
    )
    line_height = _line_height(font)
    if single_line or len(lines) * line_height <= TEXT_AREA_HEIGHT:
        return TextLayout(
            font, lines, _centred_top(len(lines) * line_height, has_footer), line_height
        )

    for size in range(MIN_FONT_SIZE, LONG_TEXT_MIN_FONT_SIZE - 1, -2):
        smaller = _load_font(size, font_path)
        if smaller is None:
            continue
        layout = _around_the_marks(text, smaller, has_footer)
        if layout is not None:
            return layout

    # Nothing fits: the last resort it has always been, running tall.
    return TextLayout(font, lines, _centred_top(len(lines) * line_height, has_footer), line_height)


@track_performance("render_card")
def render_card(
    text: str,
    bg_path: str,
    footer: str | None = None,
    watermark: str | None = None,
    single_line: bool = False,
) -> BytesIO:
    """
    Render a card with text overlaid on background.

    Args:
        text: The question/task text to render
        bg_path: Path to background image
        footer: Optional footer line (e.g. "Знакомство · 12/30") drawn near the bottom
        watermark: Optional brand line (e.g. "VECHNOST · @bot") at the bottom edge
        single_line: Never wrap or hyphen-break the text (for codes)

    Returns:
        BytesIO object containing JPEG image data
    """
    start_time = time.time()
    success = False

    try:
        # Load background image
        background = _load_background_image(bg_path)
        if not background:
            raise ValueError(f"Could not load background image: {bg_path}")

        # Create a copy to avoid modifying cached image
        card = background.copy()
        draw = ImageDraw.Draw(card)

        # Fit text clear of the corner marks, with a font that covers its
        # alphabet, centred on the card but never under the footer
        font_path = _pick_font_path(text + (footer or "") + (watermark or ""))
        layout = layout_text(
            text, font_path, has_footer=bool(footer or watermark), single_line=single_line
        )
        for line, (x, y, _, _) in zip(layout.lines, layout.line_boxes(), strict=True):
            draw.text((x, y), line, font=layout.font, fill=TEXT_COLOR)

        # Footer: theme + progress, small and quiet, bottom center
        if footer:
            footer_font = _load_font(FOOTER_FONT_SIZE, font_path)
            if footer_font:
                footer_width = _text_width(footer, footer_font)
                fx = (CARD_WIDTH - footer_width) / 2
                fy = CARD_HEIGHT - FOOTER_BOTTOM_MARGIN
                draw.text((fx, fy), footer, font=footer_font, fill=FOOTER_COLOR)

        # Brand watermark: quieter still, at the bottom edge
        if watermark:
            wm_font = _load_font(WATERMARK_FONT_SIZE, font_path)
            if wm_font:
                wm_width = _text_width(watermark, wm_font)
                wx = (CARD_WIDTH - wm_width) / 2
                wy = CARD_HEIGHT - WATERMARK_BOTTOM_MARGIN
                draw.text((wx, wy), watermark, font=wm_font, fill=WATERMARK_COLOR)

        # Convert to JPEG and return as BytesIO
        output = BytesIO()
        card.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        output.seek(0)

        success = True
        return output

    except Exception as e:
        logger.error(f"Error rendering card: {e}")
        raise
    finally:
        duration = time.time() - start_time
        log_image_rendering_event(
            success=success, duration=duration, text_length=len(text), bg_path=bg_path
        )


@lru_cache(maxsize=256)
def render_card_bytes(
    text: str,
    bg_path: str,
    footer: str | None = None,
    watermark: str | None = None,
    single_line: bool = False,
) -> bytes:
    """`render_card` as bytes, memoised.

    The deck is static, so the same card asked for twice is the same JPEG,
    and there are a few hundred of them: a cache the size of the deck means
    each is composited once per process. Callers on the event loop reach
    this through `asyncio.to_thread`, because a composite is ~25 ms of
    Pillow (145 ms cold) and used to run on the loop itself, where a burst
    of `/api/card` requests stalled webhooks and every game at once.

    Bytes rather than BytesIO so a cached value cannot be consumed by one
    reader and handed empty to the next.
    """
    return render_card(
        text, bg_path, footer=footer, watermark=watermark, single_line=single_line
    ).getvalue()


def get_background_path(topic: str, level_or_0: int, category: str) -> str:
    """
    Get the appropriate background path for a topic/level/category.

    Args:
        topic: Topic code (acq, couples, sex, prov)
        level_or_0: Level number or 0 if no levels
        category: 'q' for questions, 't' for tasks

    Returns:
        Path to background image
    """
    try:
        import yaml

        # Load background configuration
        config_path = Path(__file__).parent.parent / "assets" / "backgrounds.yml"

        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
        else:
            config = {}

        # Get map from config or use empty dict
        map_config = config.get("map", {})
        default_path = config.get("default", "assets/backgrounds/default.png")

        # Resolve path based on topic
        if topic == "sex":
            # Sex has special handling for questions/tasks
            if category in ["q", "t"] and category in map_config.get("sex", {}):
                path = map_config["sex"][category]
            elif "default" in map_config.get("sex", {}):
                path = map_config["sex"]["default"]
            else:
                path = "assets/backgrounds/sex/sex.png"
        elif topic in ["acq", "couples"]:
            # Topics with levels
            if level_or_0 > 0 and str(level_or_0) in map_config.get(topic, {}):
                path = map_config[topic][str(level_or_0)]
            else:
                path = f"assets/backgrounds/{topic}/{topic}_{level_or_0}.png"
        elif topic == "prov":
            # Provocation has no levels
            if "default" in map_config.get("prov", {}):
                path = map_config["prov"]["default"]
            else:
                path = "assets/backgrounds/prov/prov.png"
        else:
            path = default_path

        # Check if file exists, fallback to default if not
        if not Path(path).exists():
            logger.warning(f"Background not found: {path}, using default")
            path = default_path

        return path

    except Exception as e:
        logger.error(f"Error resolving background path: {e}")
        return "assets/backgrounds/default.png"
