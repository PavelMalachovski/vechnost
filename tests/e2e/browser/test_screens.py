"""Every screen, on each phone, at four sizes: the pictures a reviewer looks at.

One tour per phone model (screens.py) reaches every screen of the Mini App
for real - a partner joins through the API and the phone hears it through
its own poll - and photographs each one at 320×568, 375×667, 393×852 and
430×932. The pictures and a contact sheet land in
E2E_REPORT_DIR/browser/screens/ (index.html), and summary.md is the table CI
writes into the job summary. The tour is the `atlas` fixture (conftest.py):
one per phone, shared with the design lint that rides along.
"""

from __future__ import annotations

import pytest

from .screens import STOPS, VIEWPORTS, Atlas

pytestmark = [pytest.mark.browser, pytest.mark.screens]


def test_every_screen_is_reached_and_photographed(atlas: Atlas) -> None:
    assert not atlas.errors, "\n".join(atlas.errors)
    assert not atlas.missing, f"never reached: {atlas.missing}"
    for stop, _ in STOPS:
        assert len(atlas.shots[stop]) == len(VIEWPORTS), stop
