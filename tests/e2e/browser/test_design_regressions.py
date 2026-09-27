"""What the design audit found unreadable, measured in the browser that draws it.

Computed styles rather than CSS text: the faults were a rule that did not
reach an element (a ghost button outside an overlay), a <button> left to the
browser's defaults, a colour meant for a dark page on a light card - none of
which a grep of the stylesheet shows.
"""

from __future__ import annotations

from typing import Any

from ..harness import Server

LIGHT_CARD = (255, 229, 250)  # #FFE5FA, the printed card's ground


def _luminance(rgb: tuple[float, ...]) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(css: str) -> tuple[float, ...]:
    inside = css[css.index("(") + 1: css.index(")")]
    return tuple(float(part) for part in inside.replace("/", ",").split(",")[:4])


def _style(page: Any, html: str, selector: str, prop: str) -> str:
    """Mount `html` in the page, read one computed property of `selector`."""
    return str(page.evaluate(
        """([html, selector, prop]) => {
            const box = document.createElement('div');
            box.innerHTML = html;
            document.body.appendChild(box);
            const value = getComputedStyle(box.querySelector(selector))[prop];
            box.remove();
            return value;
        }""",
        [html, selector, prop],
    ))


def test_a_long_error_toast_fits_the_screen_and_can_be_read(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    phone.screen("home")
    box = phone.page.evaluate(
        """() => {
            const t = document.getElementById('toast');
            t.textContent = 'Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.';
            t.classList.add('show');
            const r = t.getBoundingClientRect();
            return {left: r.left, right: r.right, width: innerWidth,
                    bg: getComputedStyle(t).backgroundColor,
                    live: t.getAttribute('aria-live')};
        }"""
    )
    phone.page.wait_for_timeout(300)
    phone.shot("long-toast")
    assert box["left"] >= 0 and box["right"] <= box["width"], f"toast runs off screen: {box}"
    rgba = _rgb(box["bg"])
    assert len(rgba) == 3 or rgba[3] == 1, f"toast background is see-through: {box['bg']}"
    assert box["live"] == "polite", "screen readers are told about toasts"


def test_the_masterclass_18_plus_door_is_drawn_in_the_apps_colours(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    phone.screen("home")
    html = '<button class="guide-nsfw">Позы для неё · Контент 18+</button>'
    color = _style(phone.page, html, ".guide-nsfw", "color")
    family = _style(phone.page, html, ".guide-nsfw", "fontFamily")
    assert _rgb(color)[:3] != (0.0, 0.0, 0.0), "the browser's black on a dark page"
    assert "Arial" not in family, family


def test_a_ghost_button_outside_an_overlay_is_not_a_grey_system_button(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    phone.screen("home")
    background = phone.page.evaluate(
        "() => getComputedStyle(document.getElementById('btnS69Restart')).backgroundColor"
    )
    assert _rgb(background)[:3] != (239.0, 239.0, 239.0), f"system grey: {background}"


def test_the_secret_hint_is_readable_on_the_light_card(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    phone.screen("home")
    html = '<div class="s69-spoiler"><span class="hint">Нажмите, чтобы открыть</span></div>'
    color = _rgb(_style(phone.page, html, ".hint", "color"))
    opacity = float(_style(phone.page, html, ".hint", "opacity"))
    seen = tuple(opacity * c + (1 - opacity) * bg for c, bg in zip(color[:3], LIGHT_CARD, strict=True))
    assert _contrast(seen, LIGHT_CARD) >= 3.0, f"contrast {_contrast(seen, LIGHT_CARD):.2f}:1"
