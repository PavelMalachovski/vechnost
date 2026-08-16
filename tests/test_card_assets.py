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
