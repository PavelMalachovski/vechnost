"""The Mini App draws on the same card PNGs the bot composites.

Serving them rather than re-drawing them in CSS is the whole point: it makes
"the same card" a fact instead of a resemblance. If the mount disappears,
every card in the Mini App silently loses its art and keeps its text.
"""

import pytest
from fastapi.testclient import TestClient

from vechnost_bot.payments.web import app

CARDS = [
    "acq/acq_1.png", "acq/acq_2.png", "acq/acq_3.png",
    "couples/couples_1.png", "couples/couples_2.png", "couples/couples_3.png",
    "sex/questions.png", "sex/tasks.png", "prov/prov.png",
    "library.png", "card_back.png",
]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("card", CARDS)
def test_every_card_is_served(client, card):
    res = client.get(f"/assets/backgrounds/{card}")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


def test_the_mount_does_not_escape_the_assets_directory(client):
    res = client.get("/assets/../vechnost.db")
    assert res.status_code != 200


def test_the_mount_does_not_escape_via_percent_encoded_traversal(client):
    # httpx/requests normalise a literal ".." out of the path before the
    # request is ever sent, so the test above never actually reaches the
    # server with a traversal path — it only proves GET /vechnost.db (a
    # nonexistent route) 404s. A percent-encoded ".." survives client-side
    # normalisation and exercises StaticFiles' own traversal guard.
    res = client.get("/assets/%2e%2e/vechnost.db")
    assert res.status_code != 200
