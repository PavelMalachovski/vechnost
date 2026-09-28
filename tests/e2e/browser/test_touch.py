"""What only a finger shows: a card under real input, on both phones.

One fault in this deck was invisible to every check made from script and
obvious to anyone holding the phone. The card's back face, hidden from the
eye by `backface-visibility`, still took the compositor's hit test, so a
finger in the middle of a long card landed on a face with no scroller behind
it and the text could not be scrolled - while `elementFromPoint` kept
answering `.q-text`. A fade drawn as a mask on the scroller was blamed first
and taken off, and the rule against it stays (CLAUDE.md, "Nothing but the
front of a card may take a touch" and "A fade is an overlay, never a mask on
the scroller"; audit H-02).

So the input here is as real as each engine allows (touch.py): on the
Android phone every gesture is CDP touch, which Chromium's compositor
hit-tests and scrolls like a finger; on the iPhone a tap is WebKit's own
touchscreen, a swipe a real mouse drag, and a scroll a real press where the
finger rests followed by the arrow keys, each hit-tested by WebKit itself -
Playwright has no touch drag for WebKit and no wheel on a mobile page.

The last test turns the suite on itself: it breaks each rule on purpose and
checks that the probes here notice. On the Android phone the back face
taking touches stops the real scroll, exactly as it did in production. A
mask on the scroller no longer does - neither engine drops a masked element
from its hit test - and WebKit's own hit test skips a hidden back face, so
for the mask everywhere, and for both rules on the iPhone, the
computed-style probe is what holds the line. What each probe saw on each
phone is written to `touch-canary-<phone>.json` in the report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from ..harness import Server
from .app import (
    PROGRESS_JS,
    SMALLEST,
    TOP_CARD,
    longest_card,
    open_deck,
    progress,
    resize,
    settle_card,
    zone,
)
from .phones import REPORT_DIR, Device, Phone

# Records what every touch and click reached: which face of which card.
HITS = """() => {
  window.__hits = [];
  for (const type of ['touchstart', 'mousedown', 'click']) {
    document.addEventListener(type, (e) => {
      const t = e.target;
      const face = t.closest ? t.closest('.face') : null;
      window.__hits.push({type,
        face: face ? (face.classList.contains('front') ? 'front' : 'back') : null,
        top: !!(t.closest && t.closest('#stage .card.top')),
        tag: (t.className || t.tagName || '') + ''});
    }, true);
  }
}"""

MOVED = f"() => document.querySelector('{TOP_CARD}').style.transform"


def on_a_long_card(server: Server, phones: Any, device: Device) -> tuple[Phone, dict[str, float]]:
    """The longest card in the decks, open on a phone where it has to scroll.

    On the phone's own screen when the card overflows there, on the smallest
    phone the app supports when it does not: the content may get shorter,
    and a card that fits proves nothing about scrolling.
    """
    alice = server.player("Alice", paid=True)
    phone = phones(alice)
    card = longest_card(alice)
    open_deck(phone, card)
    band = zone(phone)
    if band["slack"] < 60:
        resize(phone, SMALLEST)
        band = zone(phone)
    assert band["slack"] > 40, (
        f"the longest card ({len(card.text)} characters) fits its band even at "
        f"{SMALLEST['width']}x{SMALLEST['height']} on {device.label}: nothing here "
        "needs scrolling any more, so this test needs a longer text to hold"
    )
    return phone, band


def scroll_probe(phone: Phone, band: dict[str, float]) -> None:
    """A finger resting where a reader's rests, the middle of the text, scrolls it."""
    phone.finger.scroll(band["x"], band["y"], band["height"] * 0.6)
    try:
        phone.page.wait_for_function(
            "(sel) => document.querySelector(sel + ' .q-zone').scrollTop > 20",
            arg=TOP_CARD,
            timeout=3_000,
        )
    except Exception as e:
        raise AssertionError(
            f"{phone.finger.kind} in the middle of a long card did not scroll its text "
            f"(scrollTop {zone(phone)['scrollTop']}): the card takes the gesture somewhere "
            "it cannot scroll - the back face, or a masked scroller"
        ) from e


def test_a_finger_scrolls_a_long_card_from_its_middle(
    server: Server, phones, device: Device
) -> None:
    """Android: a CDP touch drag, scrolled by Chromium's compositor - the test
    that fails when the card's back face takes the touch again. iPhone: a
    press at the same point, hit-tested by WebKit, then the arrow keys."""
    phone, band = on_a_long_card(server, phones, device)
    before = progress(phone)
    scroll_probe(phone, band)
    phone.shot("scrolled")
    assert progress(phone) == before, "reading the card must not turn it"
    assert phone.page.evaluate(MOVED) in ("", "none"), "reading the card must not move it"
    # The fade follows: the top edge now hides something, so it is marked.
    assert phone.page.evaluate(
        f"() => document.querySelector('{TOP_CARD} .front').classList.contains('cut-top')"
    )


def test_the_fade_follows_the_text_when_it_reflows_without_a_scroll(
    server: Server, phones, device: Device
) -> None:
    """The flags on a card's face used to change only on a scroll, a resize
    or a new card. A font that arrives late, or a stage that settles after
    the scroll, re-flows the text with none of those, and the fade stayed
    where the text had been: the WebKit screen tour once caught the long
    card with a fade band in one tour and without it in the other. The face
    now follows the text's own size."""
    phone, _ = on_a_long_card(server, phones, device)
    face = f"document.querySelector('{TOP_CARD} .front')"
    text = f"document.querySelector('{TOP_CARD} .q-text')"
    assert phone.page.evaluate(f"() => {face}.classList.contains('cut-bottom')")

    # The text shrinks until it fits: nothing is hidden, so nothing fades.
    phone.page.evaluate(f"() => {{ {text}.style.fontSize = '6px'; }}")
    phone.page.wait_for_function(
        f"() => !{face}.classList.contains('cut-bottom') && !{face}.classList.contains('cut-top')",
        timeout=3_000,
    )
    # And grows back: the bottom hides something again.
    phone.page.evaluate(f"() => {{ {text}.style.fontSize = ''; }}")
    phone.page.wait_for_function(f"() => {face}.classList.contains('cut-bottom')", timeout=3_000)


def test_a_vertical_drag_leaves_the_card_in_place(server: Server, phones, device: Device) -> None:
    """The gesture splits by axis at 8px: vertical belongs to the text, not the card."""
    phone, band = on_a_long_card(server, phones, device)
    before = progress(phone)
    text = phone.text(f"{TOP_CARD} .q-text")
    x, y = band["x"], band["y"]
    phone.finger.drag((x, y + 60), (x + 6, y - 60))
    phone.page.wait_for_timeout(700)  # longer than a card's flight
    assert progress(phone) == before
    assert phone.text(f"{TOP_CARD} .q-text") == text
    assert phone.page.evaluate(MOVED) in ("", "none")


def test_a_swipe_either_way_turns_to_the_next_card(
    server: Server, phones: Any, device: Device
) -> None:
    """«Дальше» both ways (audit D-40). Right used to be next and left went
    back, the opposite of every carousel a thumb knows, so a left swipe meant
    for the next card showed the previous one again. Back is the ↩ button."""
    phone, band = on_a_long_card(server, phones, device)
    texts = [phone.text(f"{TOP_CARD} .q-text")]
    numbers = [int(progress(phone).split(" / ")[0])]
    for direction in (1, -1):
        before = progress(phone)
        x, y, width = band["x"], band["y"], band["width"]
        phone.finger.drag((x - direction * width * 0.3, y), (x + direction * width * 0.45, y + 8))
        phone.page.wait_for_function("(t) => " + PROGRESS_JS + " !== t", arg=before, timeout=5_000)
        phone.page.wait_for_timeout(700)  # the new card turns over first
        texts.append(phone.text(f"{TOP_CARD} .q-text"))
        numbers.append(int(progress(phone).split(" / ")[0]))
        band = zone(phone)
    phone.shot("next")
    assert numbers == [numbers[0], numbers[0] + 1, numbers[0] + 2], numbers
    assert len(set(texts)) == 3, "a swipe showed a card already seen"

    # Back is a button, and it does not fly.
    phone.tap("#btnPrev")
    phone.page.wait_for_function(
        "(n) => " + PROGRESS_JS + ".startsWith(n + ' / ')", arg=numbers[1], timeout=5_000
    )
    settle_card(phone)
    assert phone.text(f"{TOP_CARD} .q-text") == texts[1]


def test_a_tap_in_the_middle_of_a_card_lands_on_its_front(
    server: Server, phones, device: Device
) -> None:
    phone, band = on_a_long_card(server, phones, device)
    phone.page.evaluate(HITS)
    phone.finger.tap(band["x"], band["y"])
    phone.page.wait_for_timeout(400)
    hits = phone.page.evaluate("() => window.__hits")
    assert any(hit["type"] == "touchstart" for hit in hits), (
        f"the tap never reached the page as a touch: {hits}"
    )
    for hit in hits:
        assert hit["top"] and hit["face"] == "front", f"a tap landed off the card's front: {hits}"


def style_probe(phone: Phone) -> None:
    """The two rules as the engine computes them: no scroller wears a mask,
    and nothing laid over the text - the back, the card beneath, the fades -
    takes a touch."""
    found = phone.page.evaluate("""() => {
        const scrollers = [...document.querySelectorAll(
          '.q-zone, #compatQuestion, #compatResultBody, .s69-card, .s69-map, .overlay, ' +
          '#home, #themeList, #levelList, .coop-box, #libraryList, #libDetailBody, #guideBody')];
        const mask = (el) => {
          const cs = getComputedStyle(el);
          return [cs.maskImage, cs.webkitMaskImage].find(v => v && v !== 'none') || null;
        };
        const card = document.querySelector('#stage .card.top');
        const front = card.querySelector('.front');
        return {
          masked: scrollers.filter(mask).map(el => (el.id || el.className) + ': ' + mask(el)),
          back: getComputedStyle(card.querySelector('.back')).pointerEvents,
          under: [...document.querySelectorAll('#stage .card.under')]
                   .map(el => getComputedStyle(el).pointerEvents),
          fades: ['::before', '::after'].map(p => getComputedStyle(front, p).pointerEvents),
        };
    }""")
    assert not found["masked"], f"a scroller carries a mask: {found['masked']}"
    assert found["back"] == "none", "the back of the card takes touches"
    assert set(found["under"]) <= {"none"}, "the card underneath takes touches"
    assert found["fades"] == ["none", "none"], "a fade over the text takes touches"


def test_no_fade_is_a_mask_and_no_back_takes_a_touch(
    server: Server, phones, device: Device
) -> None:
    """Computed styles, not the stylesheet's text: a mask or a touchable
    back from any rule counts. The backstop for what real input can only
    show on one engine (see the canary below)."""
    phone, _ = on_a_long_card(server, phones, device)
    style_probe(phone)


@dataclass(frozen=True)
class Fault:
    """One of the two CLAUDE.md hit-testing rules, broken on purpose."""

    name: str
    rule: str
    css: str  # laid over the page's own styles
    caught_by_touch: tuple[str, ...]  # engines whose real input must notice


FAULTS = [
    Fault(
        "back-takes-touches",
        "Nothing but the front of a card may take a touch",
        ".card .back { pointer-events: auto !important; }",
        # Chromium's compositor lets the back face take the gesture, which
        # is how long questions became unscrollable in production.
        caught_by_touch=("chromium",),
    ),
    Fault(
        "fade-is-a-mask",
        "A fade is an overlay, never a mask on the scroller",
        # The fade as it was before 1c68692: a gradient mask on the scroller.
        ".q-zone { -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 18px,"
        " #000 calc(100% - 18px), transparent 100%) !important;"
        " mask-image: linear-gradient(180deg, transparent 0, #000 18px,"
        " #000 calc(100% - 18px), transparent 100%) !important; }",
        # Current Chromium keeps a masked element in its hit test, so real
        # input no longer notices; the computed-style probe does.
        caught_by_touch=(),
    ),
]


@pytest.mark.parametrize("fault", FAULTS, ids=lambda fault: fault.name)
def test_the_probes_notice_each_rule_broken(
    server: Server, phones, device: Device, fault: Fault
) -> None:
    """The suite, turned on itself: break a rule and see who notices.

    Every broken rule must be noticed by some probe on every phone, and on
    the engines listed in `caught_by_touch` by real input itself. What each
    probe saw is recorded either way, so a change of engine behaviour (a
    probe that starts or stops noticing) shows up in the report.
    """
    phone, band = on_a_long_card(server, phones, device)
    phone.page.add_style_tag(content=fault.css)
    phone.page.wait_for_timeout(100)
    seen: dict[str, str] = {}
    for name, probe in (
        ("touch", lambda: scroll_probe(phone, band)),
        ("style", lambda: style_probe(phone)),
    ):
        try:
            probe()
            seen[name] = "missed"
        except AssertionError as e:
            seen[name] = "noticed: " + str(e).splitlines()[0]
        # Anything else is the probe breaking, not noticing: it propagates.
    record = REPORT_DIR / f"touch-canary-{device.name}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    report[fault.name] = {"rule": fault.rule, "input": phone.finger.kind, **seen}
    record.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    assert any(v.startswith("noticed") for v in seen.values()), (
        f"nothing noticed {fault.name!r} on {device.label}: {seen}"
    )
    if device.engine in fault.caught_by_touch:
        assert seen["touch"].startswith("noticed"), (
            f"real input on {device.label} no longer notices {fault.name!r} ({seen}): "
            "the engine changed, and the probe that guards this rule needs rethinking"
        )
