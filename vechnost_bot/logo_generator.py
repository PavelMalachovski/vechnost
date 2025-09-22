"""Logo generation for the Vechnost bot."""

from PIL import Image, ImageDraw, ImageFont
import io
from typing import Tuple


def generate_vechnost_logo(width: int = 400, height: int = 200) -> io.BytesIO:
    """Generate a stylized Vechnost logo image."""
    # Create image with dark maroon background
    background_color = (101, 28, 50)  # Dark maroon/burgundy
    image = Image.new('RGB', (width, height), background_color)
    draw = ImageDraw.Draw(image)

    # Try to use a nice font, fallback to default if not available
    try:
        # Try to use a more elegant font
        font_size = 48
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    # Calculate text position (centered)
    text = "Vechnost"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (width - text_width) // 2
    y = (height - text_height) // 2

    # Draw text with golden color and subtle glow effect
    golden_color = (255, 215, 0)  # Gold color

    # Draw glow effect (multiple slightly offset copies)
    for offset_x in range(-2, 3):
        for offset_y in range(-2, 3):
            if offset_x != 0 or offset_y != 0:
                draw.text((x + offset_x, y + offset_y), text, font=font, fill=(255, 215, 0, 50))

    # Draw main text
    draw.text((x, y), text, font=font, fill=golden_color)

    # Add some decorative elements
    # Draw subtle border
    border_color = (255, 215, 0, 100)
    draw.rectangle([5, 5, width-5, height-5], outline=border_color, width=2)

    # Convert to BytesIO
    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes


def generate_welcome_image_with_logo(text: str, language: str = "en") -> io.BytesIO:
    """Generate a welcome image with the Vechnost logo and text."""
    # Create a larger image for the welcome message
    width = 600
    height = 500

    # Background color based on language theme
    if language == "cs":
        bg_color = (240, 240, 255)  # Light blue for Czech
    elif language == "en":
        bg_color = (255, 248, 240)  # Light cream for English
    else:
        bg_color = (255, 240, 240)  # Light pink for Russian

    image = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(image)

    # Generate and paste the logo
    logo = generate_vechnost_logo(400, 120)
    logo_img = Image.open(logo)

    # Paste logo at the top
    image.paste(logo_img, (100, 20))

    # Add text below the logo with better formatting
    try:
        title_font = ImageFont.truetype("arial.ttf", 24)
        body_font = ImageFont.truetype("arial.ttf", 14)
    except (OSError, IOError):
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
            body_font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except (OSError, IOError):
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()

    # Split text into lines and draw them with proper formatting
    lines = text.split('\n')
    y_offset = 160

    for i, line in enumerate(lines):
        if line.strip():  # Skip empty lines
            # Use different fonts for different types of content
            if line.startswith('**') and line.endswith('**'):
                # This is a title
                clean_line = line.replace('**', '').replace('🎴', '').strip()
                font = title_font
                color = (101, 28, 50)  # Dark maroon
            elif line.startswith('✨'):
                # This is features section
                font = body_font
                color = (50, 50, 50)
            else:
                # Regular text
                font = body_font
                color = (70, 70, 70)

            # Calculate text position
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y_offset), line, font=font, fill=color)
            y_offset += 30 if font == title_font else 20

    # Convert to BytesIO
    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes
