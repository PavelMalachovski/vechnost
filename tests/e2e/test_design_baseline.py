"""The design lint's baseline stays a list a person can read and trust.

`tests/e2e/browser/design_baseline.json` is edited by hand: an entry is
deleted when a fault is fixed and, rarely, added when a new one is
accepted. The browser run compares the lint with it; this, in the ordinary
suite, keeps it well formed: one list per phone, every entry a rule the lint
knows at a stop the tour reaches, sorted, and none twice.
"""

from __future__ import annotations

import json

from .browser import design
from .browser.phones import DEVICES
from .browser.screens import STOPS


def test_the_baseline_names_real_rules_stops_and_phones() -> None:
    data = json.loads(design.BASELINE.read_text(encoding="utf-8"))
    phones = {key for key in data if not key.startswith("_")}
    assert phones == set(DEVICES), phones
    stops = {stop for stop, _ in STOPS}
    for phone in phones:
        entries = data[phone]
        assert entries == sorted(set(entries)), f"{phone}: keep the list sorted, each entry once"
        for entry in entries:
            rule, stop, element = entry.split(" | ")
            assert rule in design.RULES, entry
            assert stop in stops, entry
            assert element.strip() == element and element, entry
