"""The design lint: what the audit measured by hand, measured on every screen.

The screen tour (screens.py) stops at every screen and overlay of the Mini
App at four phone sizes; this visitor looks at the layer on top at each stop
- the open overlay, or else the screen - through the engine's own computed
styles, and names what breaks a rule:

* `font-size`: text under 11 px for a label (a short run of text, or text in
  a control) or 12 px for a caption (anything longer), as it renders - SVG
  text is measured at its drawn scale (audit D-12);
* `contrast`: text under WCAG AA against what is really behind it - 4.5:1,
  or 3:1 from 24 px (18.66 px bold) - with the colours of every layer under
  it composited, opacity included; a gradient counts at its worst stop, and
  text over a picture is skipped and noted rather than guessed (D-11);
* `tap-target`: a control smaller than 44×44 (D-25);
* `icon-name`: a control that shows only an icon and has no `aria-label`
  (D-14);
* `overflow`: anything that reaches past the sides of the phone;
* `clipped`: text cut off by a box that neither shows nor scrolls it.

A finding is keyed by rule, stop and element (`#id`, or the nearest id
above and the element's first class), not by size or text, so it stays the
same finding while the copy changes. `test_design_lint.py` holds the run to
a baseline of today's known findings, per phone: a new one fails, and so
does a baseline entry that no longer occurs, so the list can only shrink.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .phones import Phone
from .screens import Atlas, Viewport

BASELINE = Path(__file__).parent / "design_baseline.json"
RULES = ("font-size", "contrast", "tap-target", "icon-name", "overflow", "clipped")
# Which open audit item each rule's baseline entries belong to.
AUDIT = {"font-size": "D-12", "contrast": "D-11", "tap-target": "D-25", "icon-name": "D-14"}

LINT = r"""() => {
  const W = document.documentElement.clientWidth;
  const overlays = [...document.querySelectorAll('.overlay.show')];
  const top = overlays.length ? overlays[overlays.length - 1]
                              : document.querySelector('.screen.active');
  if (!top) return {findings: [], notes: []};
  const found = new Map();
  const notes = new Set();
  const add = (rule, el, detail) => {
    const key = rule + ' ' + sig(el);
    if (!found.has(key)) found.set(key, {rule, el: sig(el), detail});
  };

  function sig(el) {
    const tag = el.tagName.toLowerCase();
    if (el.id) return tag + '#' + el.id;
    const raw = typeof el.className === 'string' ? el.className
              : (el.className && el.className.baseVal) || '';
    const cls = raw.trim().split(/\s+/).filter(Boolean)[0];
    const anchor = el.parentElement && el.parentElement.closest('[id]');
    return (anchor ? '#' + anchor.id + ' ' : '') + tag + (cls ? '.' + cls : '');
  }

  const shown = (el) => {
    if (el.closest('.card.under, [aria-hidden="true"]')) return false;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const words = (s) => /[\p{L}\p{N}]/u.test(s || '');

  // -- colour --------------------------------------------------------------
  function rgba(s) {
    const m = /rgba?\(([^)]*)\)/.exec(s || '');
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  }
  const over = (a, b) => [0, 1, 2].map(i => a[i] * a[3] + b[i] * (1 - a[3])).concat(1);
  const lum = (c) => {
    const ch = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2]);
  };
  const ratio = (a, b) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const hex = (c) => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');

  // Everything painted under `el`, bottom to top: each element's colour and
  // gradient, faded by its own opacity and every ancestor's. A gradient is
  // every one of its stops; a picture ends the search.
  function behind(el) {
    const chain = [];
    for (let n = el; n; n = n.parentElement) chain.push(n);
    const fade = new Map();
    let product = 1;
    for (let i = chain.length - 1; i >= 0; i--) {
      product *= parseFloat(getComputedStyle(chain[i]).opacity || '1');
      fade.set(chain[i], product);
    }
    let candidates = [[255, 255, 255, 1]];
    for (let i = chain.length - 1; i >= 0; i--) {
      const n = chain[i];
      const cs = getComputedStyle(n);
      const f = fade.get(n);
      const layers = [];
      const color = rgba(cs.backgroundColor);
      if (color && color[3] > 0) layers.push([color]);
      const image = cs.backgroundImage;
      if (image && image !== 'none' && !(n === el && /text/.test(cs.webkitBackgroundClip || cs.backgroundClip))) {
        if (/url\(/.test(image)) return {picture: sig(n)};
        const stops = (image.match(/rgba?\([^)]*\)/g) || []).map(rgba).filter(Boolean);
        if (stops.length) layers.push(stops);
      }
      for (const stops of layers) {
        const next = [];
        for (const s of stops) for (const b of candidates) next.push(over([s[0], s[1], s[2], s[3] * f], b));
        const seen = new Set();
        candidates = next.filter(c => { const k = c.slice(0, 3).map(Math.round).join(); return seen.has(k) ? false : seen.add(k); }).slice(0, 48);
      }
    }
    return {candidates, fade: fade.get(el)};
  }

  // -- text ----------------------------------------------------------------
  const texts = [top, ...top.querySelectorAll('*')].filter(el =>
    [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && shown(el));
  for (const el of texts) {
    const text = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim();
    if (!words(text)) continue;          // an icon or an emoji: not text to read
    const cs = getComputedStyle(el);
    const svg = el instanceof SVGElement;
    let size = parseFloat(cs.fontSize);
    if (svg && el.getScreenCTM) {
      const m = el.getScreenCTM();
      if (m) size *= Math.sqrt(m.a * m.a + m.b * m.b);
    }
    const control = !!el.closest('button, summary, [role=button], .chip');
    const label = control || text.length <= 24;
    const floor = label ? 11 : 12;
    if (size < floor - 0.05) {
      add('font-size', el, `${size.toFixed(1)} px ${label ? 'label' : 'caption'} (floor ${floor})`);
    }

    if (el.closest('button:disabled')) continue;  // WCAG: inactive controls are exempt
    const clip = /text/.test(cs.webkitBackgroundClip || cs.backgroundClip);
    let inks = clip ? (cs.backgroundImage.match(/rgba?\([^)]*\)/g) || []).map(rgba).filter(Boolean)
                    : [rgba(svg ? cs.fill : cs.color)];
    inks = inks.filter(Boolean);
    const under = behind(el);
    if (under.picture) { notes.add(`text over a picture: ${sig(el)} on ${under.picture}`); }
    else if (inks.length) {
      const weight = parseInt(cs.fontWeight, 10) || 400;
      const large = size >= 24 || (size >= 18.66 && weight >= 700);
      const need = large ? 3 : 4.5;
      let worst = null;
      for (const ink of inks) for (const bg of under.candidates) {
        const fg = over([ink[0], ink[1], ink[2], ink[3] * under.fade], bg);
        const r = ratio(fg, bg);
        if (!worst || r < worst.r) worst = {r, fg, bg};
      }
      if (worst && worst.r < need - 0.005) {
        add('contrast', el, `${worst.r.toFixed(2)}:1 (${hex(worst.fg)} on ${hex(worst.bg)}, needs ${need}:1)`);
      }
    }

    // Clipped: text reaching past an ancestor that hides overflow on that
    // axis. A scroller in between makes it reachable, and ends the search.
    const range = document.createRange();
    range.selectNodeContents(el);
    const box = range.getBoundingClientRect();
    for (const axis of ['x', 'y']) {
      for (let p = el; p && p !== document.body; p = p.parentElement) {
        const ov = getComputedStyle(p)[axis === 'x' ? 'overflowX' : 'overflowY'];
        if (ov === 'auto' || ov === 'scroll') break;
        if (ov !== 'hidden' && ov !== 'clip') continue;
        const r = p.getBoundingClientRect();
        const out = axis === 'x' ? (box.left < r.left - 1 || box.right > r.right + 1)
                                 : (box.top < r.top - 1 || box.bottom > r.bottom + 1);
        if (out) {
          add('clipped', el, `text ${Math.round(box.left)}..${Math.round(box.right)} x ` +
              `${Math.round(box.top)}..${Math.round(box.bottom)} cut by ${sig(p)}`);
          break;
        }
      }
    }
  }

  // -- controls ------------------------------------------------------------
  const controls = [top, ...top.querySelectorAll('*')].filter(el =>
    (el.matches('button, a[href], summary, [role=button], input, select, textarea')
     || typeof el.onclick === 'function') && shown(el) && !el.disabled);
  for (const el of controls) {
    if (el === top) continue;                    // an overlay closes on a tap beside its card
    const r = el.getBoundingClientRect();
    if (r.width < 44 - 0.5 || r.height < 44 - 0.5) {
      add('tap-target', el, `${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    const name = (el.getAttribute('aria-label') || '').trim() ||
                 (el.getAttribute('aria-labelledby') || '').trim();
    if (!words(el.innerText || el.textContent) && !name) {
      add('icon-name', el, JSON.stringify((el.innerText || el.textContent || '').trim()));
    }
  }

  // -- overflow ------------------------------------------------------------
  for (const el of [top, ...top.querySelectorAll('*')]) {
    if (el.closest('.card') || el.classList.contains('confetti')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || (r.right <= W + 1 && r.left >= -1)) continue;
    if (!shown(el)) continue;
    let scroller = false;
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(p).overflowX)) { scroller = true; break; }
    }
    if (!scroller) add('overflow', el, `${Math.round(r.left)}..${Math.round(r.right)} of ${W}`);
  }

  return {findings: [...found.values()], notes: [...notes]};
}"""


def lint(phone: Phone) -> dict[str, Any]:
    """What breaks a rule on the layer this phone shows now."""
    return dict(phone.page.evaluate(LINT))


def visitor(atlas: Atlas, stop: str, phone: Phone, viewport: Viewport) -> None:
    """A tour visitor: the lint's findings at every stop and size."""
    atlas.note(stop, viewport, "design", lint(phone))


def findings(atlas: Atlas) -> dict[str, dict[str, str]]:
    """Every finding of a tour, `rule | stop | element` -> where and what.

    A finding counts once however many sizes show it; the detail says the
    sizes, so a size-dependent one reads as such.
    """
    found: dict[str, dict[str, Any]] = {}
    for stop, sizes in atlas.notes.items():
        for size, notes in sizes.items():
            for item in notes.get("design", {}).get("findings", []):
                key = f"{item['rule']} | {stop} | {item['el']}"
                entry = found.setdefault(key, {"sizes": [], "detail": item["detail"]})
                entry["sizes"].append(size)
    return {
        key: {"detail": value["detail"], "sizes": ", ".join(value["sizes"])}
        for key, value in sorted(found.items())
    }


def picture_notes(atlas: Atlas) -> list[str]:
    """What the contrast rule skipped because the text sits on a picture."""
    seen: set[str] = set()
    for sizes in atlas.notes.values():
        for notes in sizes.values():
            seen.update(notes.get("design", {}).get("notes", []))
    return sorted(seen)


def load_baseline() -> dict[str, list[str]]:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {phone: list(entries) for phone, entries in data.items() if not phone.startswith("_")}
