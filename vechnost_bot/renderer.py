"""Image rendering module for Vechnost bot cards."""

import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Constants
CARD_WIDTH = 1080
CARD_HEIGHT = 1350
PADDING = 20
TEXT_MARGIN = 0.9  # 90% of image width for larger text
LINE_SPACING = 1.25
JPEG_QUALITY = 90
DEFAULT_FONT_SIZE = 80
MIN_FONT_SIZE = 80

# Font path
FONT_PATH = Path(__file__).parent.parent / "assets" / "fonts" / "Montserrat-Regular.ttf"


@lru_cache(maxsize=32)
def _load_background_image(bg_path: str) -> Optional[Image.Image]:
    """Load and cache background image."""
    try:
        path = Path(bg_path)
        if not path.exists():
            logger.warning(f"Background image not found: {bg_path}")
            return None

        image = Image.open(path)
        # Convert to RGB if necessary (for JPEG output)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Resize to target dimensions if needed
        if image.size != (CARD_WIDTH, CARD_HEIGHT):
            image = image.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)

        return image
    except Exception as e:
        logger.error(f"Error loading background image {bg_path}: {e}")
        return None


@lru_cache(maxsize=128)
def _load_font(size: int) -> Optional[ImageFont.FreeTypeFont]:
    """Load and cache font at specific size."""
    try:
        # Try Montserrat first
        if FONT_PATH.exists():
            return ImageFont.truetype(str(FONT_PATH), size)

        # Try system fonts that are similar to Montserrat
        system_fonts = [
            "C:/Windows/Fonts/arial.ttf",  # Arial is similar to Montserrat
            "arial.ttf",
            "Arial.ttf",
            "calibri.ttf",
            "Calibri.ttf",
            "verdana.ttf",
            "Verdana.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc"
        ]

        for font_name in system_fonts:
            try:
                return ImageFont.truetype(font_name, size)
            except:
                continue

        # Last resort: use default font
        logger.warning(f"Font file not found: {FONT_PATH}, using default font")
        return ImageFont.load_default()
    except Exception as e:
        logger.error(f"Error loading font at size {size}: {e}")
        return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = font.getbbox(test_line)
        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                # Single word is too long, force it
                lines.append(word)

    if current_line:
        lines.append(' '.join(current_line))

    return lines


def _calculate_text_dimensions(lines: list[str], font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """Calculate total width and height of text lines."""
    if not lines:
        return 0, 0

    max_width = 0
    total_height = 0

    for line in lines:
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]

        max_width = max(max_width, line_width)
        total_height += int(line_height * LINE_SPACING)

    return max_width, total_height


def _find_optimal_font_size(text: str, max_width: int, max_height: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Find the largest font size that fits the text within constraints."""
    font_size = DEFAULT_FONT_SIZE

    while font_size >= MIN_FONT_SIZE:
        font = _load_font(font_size)
        if not font:
            break

        lines = _wrap_text(text, font, max_width)
        text_width, text_height = _calculate_text_dimensions(lines, font)

        if text_height <= max_height:
            return font, lines

        font_size -= 50

    # If we can't fit even with minimum font size, return minimum
    font = _load_font(MIN_FONT_SIZE)
    lines = _wrap_text(text, font, max_width)
    return font, lines


def render_card(text: str, bg_path: str, footer: Optional[str] = None) -> BytesIO:
    """
    Render a card with text overlaid on background.

    Args:
        text: The question/task text to render
        bg_path: Path to background image
        footer: Optional footer text (not used in current implementation)

    Returns:
        BytesIO object containing JPEG image data
    """
    try:
        # Load background image
        background = _load_background_image(bg_path)
        if not background:
            raise ValueError(f"Could not load background image: {bg_path}")

        # Create a copy to avoid modifying cached image
        card = background.copy()
        draw = ImageDraw.Draw(card)

        # Calculate text area
        text_area_width = int(CARD_WIDTH * TEXT_MARGIN)
        text_area_height = CARD_HEIGHT - (2 * PADDING)

        # Find optimal font size and wrap text
        font, lines = _find_optimal_font_size(text, text_area_width, text_area_height)

        # Calculate text position (centered)
        _, total_text_height = _calculate_text_dimensions(lines, font)
        start_y = (CARD_HEIGHT - total_text_height) // 2

        # No background overlay - text will be rendered directly on the card

        # Draw text lines
        current_y = start_y
        for line in lines:
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
            x = (CARD_WIDTH - line_width) // 2  # Center horizontally
            y = current_y

            # Draw text with strong shadow for better readability without background
            draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0, 255))  # Strong shadow
            draw.text((x, y), line, font=font, fill=(245, 160, 227, 255))  # Main text - #F5A0E3

            current_y += int((bbox[3] - bbox[1]) * LINE_SPACING)

        # Convert to JPEG and return as BytesIO
        output = BytesIO()
        card.save(output, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        output.seek(0)

        return output

    except Exception as e:
        logger.error(f"Error rendering card: {e}")
        raise


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
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        else:
            config = {}

        # Get map from config or use empty dict
        map_config = config.get('map', {})
        default_path = config.get('default', 'assets/backgrounds/default.png')

        # Resolve path based on topic
        if topic == 'sex':
            # Sex has special handling for questions/tasks
            if category in ['q', 't'] and category in map_config.get('sex', {}):
                path = map_config['sex'][category]
            elif 'default' in map_config.get('sex', {}):
                path = map_config['sex']['default']
            else:
                path = f"assets/backgrounds/sex/sex.png"
        elif topic in ['acq', 'couples']:
            # Topics with levels
            if level_or_0 > 0 and str(level_or_0) in map_config.get(topic, {}):
                path = map_config[topic][str(level_or_0)]
            else:
                path = f"assets/backgrounds/{topic}/{topic}_{level_or_0}.png"
        elif topic == 'prov':
            # Provocation has no levels
            if 'default' in map_config.get('prov', {}):
                path = map_config['prov']['default']
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
