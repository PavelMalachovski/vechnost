"""The Mini App draws on the same card PNGs the bot composites.

Serving them rather than re-drawing them in CSS is the whole point: it makes
"the same card" a fact instead of a resemblance. If the mount disappears,
every card in the Mini App silently loses its art and keeps its text.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vechnost_bot.payments.web import app

INDEX = Path(__file__).parent.parent / "webapp" / "index.html"

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


def test_the_mini_app_points_at_the_real_card_art():
    html = INDEX.read_text(encoding="utf-8")
    assert "/assets/backgrounds/" in html
    assert "card_back.png" in html


def test_the_mini_app_no_longer_ships_the_old_typography():
    """Montserrat and Georgia are gone; the cards are set in the brand three."""
    html = INDEX.read_text(encoding="utf-8")
    assert "Montserrat" not in html
    assert "Georgia" not in html
    for family in ("Inter", "Lora", "Forum"):
        assert family in html


def test_the_mini_app_suits_match_the_printed_cards():
    """acq ♥, couples ♠, sex ♣, prov ♦ — the art, not the old guess."""
    html = INDEX.read_text(encoding="utf-8")
    line = next(line for line in html.splitlines() if "const SUITS" in line)
    assert "'Acquaintance': '♥'" in line
    assert "'For Couples': '♠'" in line
    assert "'Sex': '♣'" in line
    assert "'Provocation': '♦'" in line


def test_every_deck_face_the_mini_app_names_is_a_file_that_exists():
    """CARD_ART must not drift from the PNGs the server actually serves."""
    html = INDEX.read_text(encoding="utf-8")
    backgrounds = Path(__file__).parent.parent / "assets" / "backgrounds"
    named = set(re.findall(r"'((?:acq|couples|sex|prov)/[a-z_0-9]+\.png)'", html))
    assert named == {c for c in CARDS if "/" in c}
    for rel in named:
        assert (backgrounds / rel).is_file()


def test_the_sex_deck_is_keyed_by_the_content_type_the_app_actually_uses():
    """S.type is 'questions'/'tasks'; a 'q'/'t' key would never match."""
    html = INDEX.read_text(encoding="utf-8")
    assert "questions: 'sex/questions.png'" in html
    assert "tasks: 'sex/tasks.png'" in html


def test_couple_mode_sets_the_state_the_card_art_is_chosen_from():
    """enterCoopDeck used to copy only the theme; level and type are needed too."""
    html = INDEX.read_text(encoding="utf-8")
    body = html.split("function enterCoopDeck()")[1].split("\n  }")[0]
    assert "S.theme = C.st.theme" in body
    assert "S.level = C.st.level" in body
    assert "S.type = C.st.type" in body
