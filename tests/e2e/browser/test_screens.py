"""Every screen, on each phone, at four sizes: the pictures a reviewer looks at.

One tour per phone model (screens.py) reaches every screen of the Mini App
for real - a partner joins through the API and the phone hears it through
its own poll - and photographs each one at 320×568, 375×667, 393×852 and
430×932. The pictures and a contact sheet land in
E2E_REPORT_DIR/browser/screens/ (index.html), and summary.md is the table CI
writes into the job summary.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from ..harness import Server
from .phones import DEVICES, PHONES, Engines, bot_token
from .screens import STOPS, VIEWPORTS, Atlas, Tour, save_atlas

pytestmark = [pytest.mark.browser, pytest.mark.screens]


@pytest.fixture(scope="session", params=[device.name for device in PHONES])
def atlas(request: pytest.FixtureRequest, engines: Engines, live_url: str) -> Iterator[Atlas]:
    """One tour of every screen per phone model, shared by whatever inspects it."""
    device = DEVICES[request.param]
    engines.get(device.engine)
    with httpx.Client(base_url=live_url, timeout=30) as http:
        found = Tour(engines, live_url, Server(http, live=True, bot_token=bot_token()), device).run()
    save_atlas(found)
    yield found


def test_every_screen_is_reached_and_photographed(atlas: Atlas) -> None:
    assert not atlas.errors, "\n".join(atlas.errors)
    assert not atlas.missing, f"never reached: {atlas.missing}"
    for stop, _ in STOPS:
        assert len(atlas.shots[stop]) == len(VIEWPORTS), stop
