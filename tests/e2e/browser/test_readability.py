"""The Mini App as drawn on a phone: one Back, answers that can be changed,
the masterclass on a narrow screen, and no text too small to read.

The static checks in tests/test_webapp_readability.py read the source;
these read what the browser actually lays out (audit D-12, D-21, D-23,
D-25; D-20 is in test_two_phones.py, where there are two phones).
"""

from __future__ import annotations

import json

from ..harness import Server

POLL = 12_000

# Opens the page as a plain browser would, outside Telegram: the stub is
# still loaded, but says it runs on no known platform.
OUTSIDE_TELEGRAM = """
(() => {
  let telegram;
  Object.defineProperty(window, 'Telegram', {
    configurable: true,
    get() { return telegram; },
    set(value) { if (value && value.WebApp) value.WebApp.platform = 'unknown'; telegram = value; },
  });
})();
"""

# Every piece of visible text on the active screen that is drawn under 11px.
# SVG text is measured as drawn: its font-size is in the drawing's units.
TOO_SMALL = """() => {
  const screen = document.querySelector('.screen.active');
  const small = [];
  for (const el of screen.querySelectorAll('*')) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const box = el.getBoundingClientRect();
    if (!box.width || !box.height) continue;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    let px = parseFloat(style.fontSize);
    if (el instanceof SVGElement && el.getScreenCTM) px *= el.getScreenCTM().a;
    if (px < 10.95) small.push([el.className && el.className.baseVal !== undefined
      ? el.className.baseVal : el.className, el.textContent.trim().slice(0, 20), px]);
  }
  return small;
}"""


def press_back(phone) -> None:
    phone.page.evaluate("() => window.Telegram.WebApp.BackButton._cb()")


def test_inside_telegram_there_is_one_back(server: Server, phones) -> None:
    """Telegram's header has a Back; the page's own «←» is hidden, and
    Telegram's does what it did (audit D-25)."""
    phone = phones(server.player("Alice"))
    phone.screen("home")
    phone.page.click("#btnPlay")
    phone.screen("themes")
    assert (
        phone.page.evaluate(
            "() => getComputedStyle(document.getElementById('backHome')).visibility"
        )
        == "hidden"
    )
    size = phone.page.evaluate(
        "() => { const r = document.getElementById('btnPlay').getBoundingClientRect(); return r.height; }"
    )
    assert size >= 44
    press_back(phone)
    phone.screen("home")


def test_outside_telegram_the_page_keeps_its_own_back(server: Server, phones) -> None:
    phone = phones(server.player("Alice"), init_script=OUTSIDE_TELEGRAM)
    phone.screen("home")
    phone.page.click("#btnPlay")
    phone.screen("themes")
    phone.page.click("#backHome")
    phone.screen("home")


def test_an_answer_can_be_changed_until_both_have_finished(server: Server, phones) -> None:
    """Back one question shows the answer given, and a new one is sent for
    that question (audit D-21). The server never sends values back, so what
    is checked is what the phone sends."""
    alice, bob = server.player("Alice", paid=True), server.player("Bob")
    test = alice.ok("POST", "/api/compat", None)
    bob.ok("POST", f"/api/compat/{test['code']}/join")

    phone = phones(alice, start_param=f"cmp_{test['code']}")
    phone.screen("compatQuiz")
    assert (
        not phone.page.is_visible("#compatPrev")
        or phone.page.evaluate(
            "() => getComputedStyle(document.getElementById('compatPrev')).visibility"
        )
        == "hidden"
    )

    options = "#compatScale .compat-opt"
    phone.page.locator(options).nth(3).click()  # question 1: «Скорее да»
    phone.page.wait_for_function(
        "() => document.getElementById('compatProgressNum').innerText.trim().startsWith('2 /')"
    )
    phone.page.wait_for_selector(f"{options}:not([disabled])")
    phone.page.locator(options).nth(1).click()  # question 2: «Скорее нет»
    phone.page.wait_for_function(
        "() => document.getElementById('compatProgressNum').innerText.trim().startsWith('3 /')"
    )
    phone.page.wait_for_selector("#compatPrev:not([disabled])")

    phone.page.click("#compatPrev")
    phone.page.wait_for_function(
        "() => document.getElementById('compatProgressNum').innerText.trim().startsWith('2 /')"
    )
    checked = phone.page.locator(f'{options}[aria-checked="true"]')
    assert checked.count() == 1 and checked.first.get_attribute("data-value") == "2"
    phone.shot("compat-back-one")

    with phone.page.expect_request(lambda r: "/answer" in r.url and r.method == "POST") as sent:
        phone.page.locator(options).nth(4).click()  # changed: «Полностью да»
    assert json.loads(sent.value.post_data) == {"index": 1, "value": 5}
    phone.page.wait_for_function(
        "() => document.getElementById('compatProgressNum').innerText.trim().startsWith('3 /')"
    )
    assert alice.ok("GET", f"/api/compat/{test['code']}")["answered_indices"] == [0, 1]


def _open_masterclass(phone) -> None:
    phone.screen("home")
    phone.page.click('[data-module="nude_guide"]')
    phone.page.wait_for_selector("#nsfw.show, #guide.active")
    if phone.page.is_visible("#nsfwYes"):
        phone.page.click("#nsfwYes")
    phone.screen("guide")
    phone.page.wait_for_selector("#guide .guide-item")


def test_the_masterclass_puts_the_drawing_above_the_words_on_a_narrow_phone(
    server: Server, phones
) -> None:
    """At 320px the drawing's column left the words about 110px (D-23)."""
    phone = phones(server.player("Alice", paid=True))
    phone.page.set_viewport_size({"width": 320, "height": 568})
    _open_masterclass(phone)
    columns = phone.page.evaluate(
        "() => getComputedStyle(document.querySelector('#guide .guide-item')).gridTemplateColumns"
    )
    assert len(columns.split()) == 1, columns
    words = phone.page.evaluate(
        "() => document.querySelector('#guide .guide-item-text').getBoundingClientRect().width"
    )
    assert words > 220
    phone.shot("masterclass-320")

    phone.page.set_viewport_size({"width": 390, "height": 844})
    columns = phone.page.evaluate(
        "() => getComputedStyle(document.querySelector('#guide .guide-item')).gridTemplateColumns"
    )
    assert columns.split()[0] == "136px", columns


def test_no_text_is_drawn_under_eleven_pixels(server: Server, phones) -> None:
    """The board's labels were 7.5px and the drawings' notes about 9px on a
    page that could not be zoomed (D-12)."""
    alice, bob = server.player("Alice", paid=True), server.player("Bob")
    for width in (320, 390):
        phone = phones(alice)
        phone.page.set_viewport_size({"width": width, "height": 700})
        phone.screen("home")
        assert phone.page.evaluate(TOO_SMALL) == []
        phone.page.click("#btnPlay")
        phone.screen("themes")
        assert phone.page.evaluate(TOO_SMALL) == []
        press_back(phone)
        _open_masterclass(phone)
        assert phone.page.evaluate(TOO_SMALL) == [], width

    game = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})
    bob.ok("POST", f"/api/steps69/{game['code']}/join", {})
    board = phones(alice, start_param=f"s69_{game['code']}")
    board.page.set_viewport_size({"width": 320, "height": 568})
    board.page.wait_for_selector("#nsfw.show, #s69Board.active")
    if board.page.is_visible("#nsfwYes"):
        board.page.click("#nsfwYes")
    board.screen("s69Board", timeout=POLL)
    board.page.wait_for_selector("#s69Map .s69-mark")
    assert board.page.evaluate(TOO_SMALL) == []
    board.shot("board-320")
