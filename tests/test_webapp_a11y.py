"""What the Mini App gives a keyboard and a screen reader (audit D-14).

Read off the page's own source, like tests/test_webapp_readability.py; the
browser test (tests/e2e/browser/test_keyboard.py) presses the keys.

- Every screen has one h1: its title, or the wordmark on the home screen.
- Every layer is a modal dialog labelled by its own heading, and can take
  the focus (tabindex -1): `trackLayerFocus` moves it in and back out.
- A button that shows only a sign (↩, →, 🔀, 🗺) says what it does, by
  an I18N key that `applyI18n` sets as its aria-label.
- Keyboard focus is visible, drawn with the design token for it.
"""

import re
from pathlib import Path

INDEX = Path(__file__).parent.parent / "webapp" / "index.html"
HTML = INDEX.read_text(encoding="utf-8")
BODY = HTML.split("<body", 1)[1].split("<script", 1)[0]
I18N = HTML.split("const I18N = {", 1)[1].split("\n  };", 1)[0]
STYLE = re.sub(r"/\*.*?\*/", "", HTML.split("<style>", 1)[1].split("</style>", 1)[0], flags=re.S)


def _attrs(tag: str) -> dict[str, str]:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', tag))


def _screens() -> dict[str, str]:
    return {
        match.group(1): BODY[match.start() : BODY.index("</section>", match.start())]
        for match in re.finditer(r'<section class="screen[^"]*" id="([^"]+)"', BODY)
    }


def _layers() -> dict[str, tuple[dict[str, str], str]]:
    """Each overlay's opening tag and its markup, up to the next overlay."""
    starts = list(re.finditer(r'<div class="overlay"[^>]*>', BODY))
    layers = {}
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(BODY)
        attrs = _attrs(match.group(0))
        layers[attrs["id"]] = (attrs, BODY[match.end() : end])
    return layers


def test_every_screen_has_one_h1():
    screens = _screens()
    assert len(screens) >= 17
    for screen, markup in screens.items():
        assert markup.count("<h1") == 1, screen
    assert '<h1 class="logo">' in screens["home"]


def test_every_layer_is_a_labelled_modal_dialog():
    layers = _layers()
    assert len(layers) >= 7
    for layer, (attrs, markup) in layers.items():
        assert attrs.get("role") == "dialog", layer
        assert attrs.get("aria-modal") == "true", layer
        assert attrs.get("tabindex") == "-1", layer
        heading = attrs.get("aria-labelledby")
        assert heading and f'id="{heading}"' in markup, (layer, heading)


def test_a_button_that_shows_only_a_sign_says_what_it_does():
    """Its text has no letter in it - an arrow, an emoji - so a screen
    reader would read out the sign's name, or nothing."""
    unnamed = []
    for tag, content in re.findall(r"(<button[^>]*>)(.*?)</button>", BODY, re.S):
        attrs = _attrs(tag)
        text = re.sub(r"<[^>]+>", "", content).strip()
        if not text or re.search(r"[A-Za-zА-Яа-яЁё]", text) or "data-i18n" in attrs:
            continue  # it has words, or gets them from I18N or at run time
        if not (attrs.get("aria-label") or attrs.get("data-i18n-aria")):
            unnamed.append((attrs.get("id"), text))
    assert unnamed == []


def test_every_spoken_label_is_in_i18n():
    keys = re.findall(r'data-i18n-aria="([^"]+)"', BODY)
    assert len(keys) >= 7
    for key in keys:
        assert re.search(rf"\b{key}:\s*'[^']+'", I18N), key
    assert "setAttribute('aria-label'" in HTML


def test_keyboard_focus_is_visible_and_reads_its_token():
    rules = re.findall(r"([^{}]*:focus-visible[^{}]*)\{([^{}]*)\}", STYLE)
    assert any("var(--focus-ring)" in body for _, body in rules), rules
    assert re.search(r"--focus-ring:", STYLE)


def test_the_keys_have_somewhere_to_go():
    """The browser test presses them; this only says the page listens."""
    assert "addEventListener('keydown'" in HTML
    for key in ("'Escape'", "'Tab'", "'ArrowLeft'", "'ArrowRight'"):
        assert key in HTML, key
