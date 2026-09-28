"""What the Mini App asks of a reader's eyes and thumbs.

Read off the page's own source, like tests/test_webapp_static.py: the rules
here hold for every screen at once, and the browser tests
(tests/e2e/browser/test_readability.py) check the same things as drawn.

- D-11: the text on a theme tile has to read on every stop of the tile's
  gradient. White went down to 1.65:1 on the light end of «Знакомство».
- D-12: nothing is set under 11px, and the page may be zoomed. Labels on
  the «69» board were 7.5px on a page that refused to scale.
- D-25: one Back, and nothing pressable smaller than a thumb.
"""

import re
from pathlib import Path

INDEX = Path(__file__).parent.parent / "webapp" / "index.html"
HTML = INDEX.read_text(encoding="utf-8")
STYLE = re.sub(r"/\*.*?\*/", "", HTML.split("<style>", 1)[1].split("</style>", 1)[0], flags=re.S)


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", STYLE)
    assert match, selector
    return match.group(1)


def test_the_page_may_be_zoomed():
    viewport = re.search(r'<meta name="viewport" content="([^"]+)"', HTML).group(1)
    assert "user-scalable=no" not in viewport
    assert "maximum-scale" not in viewport


def test_no_text_is_set_under_eleven_pixels():
    """`.art-note` is the one size in SVG units, not pixels: 10 of a
    120-unit drawing, drawn at least 136px wide, is 11.3px on screen (the
    browser test measures it)."""
    small = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", STYLE):
        for size in re.findall(r"font-size:\s*([\d.]+)px", body):
            if float(size) < 11 and selector.strip() != ".art-note":
                small.append((selector.strip(), size))
    assert small == []
    assert float(re.search(r"font-size:\s*([\d.]+)px", _rule(".art-note")).group(1)) >= 10


def test_tile_text_reads_on_every_stop_of_its_gradient():
    ink = re.search(r"--c-ink:\s*(#[0-9A-Fa-f]{6})", HTML).group(1)
    for tile in ("g-acq", "g-couples", "g-sex", "g-prov"):
        body = _rule(f".{tile}")
        stops = re.findall(
            r"#[0-9A-Fa-f]{6}", body.split("color:")[0] if "color:" in body else body
        )
        text = ink if "var(--ink)" in body else "#FFFFFF"
        worst = min(_contrast(text, stop) for stop in stops)
        # 13px tile descriptions and 11px counts: normal text, so AA is 4.5.
        assert worst >= 4.5, (tile, text, round(worst, 2))


def test_tile_text_is_never_faded():
    for selector in (".theme-card .t-desc", ".theme-card .t-count"):
        assert "opacity" not in _rule(selector), selector


def test_nothing_pressable_is_smaller_than_a_thumb():
    assert re.search(r"--tap-min:\s*44px", STYLE)
    icon = _rule(".icon-btn")
    assert "width: var(--tap-min)" in icon and "height: var(--tap-min)" in icon
    assert "min-height: var(--tap-min)" in _rule("button.chip")
    assert "min-height:var(--tap-min)" in _rule(".compat-qi summary")
    assert "min-height:var(--tap-min)" in _rule(".compat-opt")


def test_every_header_back_is_named_and_telegram_s_back_presses_it():
    backs = re.findall(
        r'<button class="icon-btn back" id="(\w+)" aria-label="Назад">←</button>', HTML
    )
    assert len(backs) == 16
    # Any «←» left without the class would be neither hidden in Telegram
    # nor reachable by Telegram's own Back.
    assert re.findall(r'<button class="icon-btn" id="\w+">←</button>', HTML) == []
    assert "document.querySelector('.screen.active .top .icon-btn.back')" in HTML
    assert "html.tg-back .top .icon-btn.back { visibility: hidden; }" in HTML
