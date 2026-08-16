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


def _css_block(html: str, selector: str) -> str:
    """The declarations of the first rule for `selector`."""
    return html.split(selector + " {", 1)[1].split("}", 1)[0]


def test_long_card_text_scrolls_instead_of_shrinking():
    """A question longer than the card used to shrink to 15.5px and still
    overrun the footer. Now the text area scrolls and the size holds."""
    html = INDEX.read_text(encoding="utf-8")
    assert ".q-text.tiny" not in html
    assert ".q-text.small" not in html
    q_zone = _css_block(html, ".q-zone")
    assert "overflow-y" in q_zone
    # #stage is touch-action: none, which would otherwise swallow the pan
    # that scrolls this zone on a touch screen.
    assert "touch-action" in q_zone
    q_text = _css_block(html, ".q-text")
    assert "font-size: 22px" in q_text


def test_the_fade_marks_only_an_edge_that_actually_hides_something():
    """A fade that is always on dims the first line of an unscrolled card and
    the last line at the end — the rendering fault it exists to prevent."""
    html = INDEX.read_text(encoding="utf-8")
    assert "mask-image" in _css_block(html, ".q-zone")
    assert ".q-zone.cut-top {" in html
    assert ".q-zone.cut-bottom {" in html
    assert "function markZoneEdges" in html
    # Global hooks, so a deck that does not know about them still gets it.
    assert "MutationObserver(refreshZoneEdges)" in html


def test_the_stage_still_blocks_horizontal_panning_but_allows_vertical():
    """touch-action: none on #stage cancels the vertical pan the card text
    needs; pan-y keeps the horizontal block that protects the swipe."""
    html = INDEX.read_text(encoding="utf-8")
    stage = _css_block(html, "#stage")
    assert "touch-action: pan-y" in stage


def test_a_vertical_drag_scrolls_the_text_instead_of_dragging_the_card():
    """Without an axis lock, reading a long question drags the card away."""
    html = INDEX.read_text(encoding="utf-8")
    assert "axis: null" in html
    move = html.split("function dragMove(")[1].split("\n  }")[0]
    assert "drag.axis" in move
    assert "if (drag.axis === 'y') return;" in move
    end = html.split("function dragEnd(")[1].split("\n  }")[0]
    assert "drag.axis === 'y'" in end


def test_the_library_has_a_deck_screen():
    """Every Library module is read as cards now, on the Library face."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="libDeck"' in html
    assert 'id="libStage"' in html
    assert "libDeckOpen" in html
    assert "LIBRARY_ART" in html


def test_the_library_no_longer_renders_bare_lists():
    html = INDEX.read_text(encoding="utf-8")
    assert "<ol>" not in html
    assert "lib-daily" not in html
    assert "lib-question" not in html


def test_the_library_deck_stands_on_the_same_geometry_as_the_game_deck():
    """#libStage is a second stage, not a second set of rules for one."""
    html = INDEX.read_text(encoding="utf-8")
    assert _css_block(html, "#stage") == _css_block(html, "#libStage")


def test_the_library_deck_hands_the_swipe_engine_its_own_transitions():
    """flyOut() ends in the game's S/COOP state unless told otherwise, and
    dragEnd decides 'can I go back?' from S.idx. Both must ask the Library."""
    html = INDEX.read_text(encoding="utf-8")
    end = html.split("function dragEnd(")[1].split("\n  }")[0]
    assert "LS.idx" in end
    fly = html.split("function flyOut(")[1].split("\n  }")[0]
    assert "drag.onAdvance" in fly
    # Stale callbacks would send a game swipe into the Library.
    for fn in ("function enterDeck(", "function enterCoopDeck("):
        assert "drag.onAdvance = null" in html.split(fn)[1].split("\n  }")[0]


def test_a_truncated_library_deck_says_so_on_its_last_card():
    """A practice module has no category screen to hang the paywall on, so
    the deck itself must end on the prompt rather than just stopping."""
    html = INDEX.read_text(encoding="utf-8")
    assert "libLockCard" in html


def test_the_home_screen_shows_decks_not_typographic_suits():
    """The first thing the Mini App shows should be the game, not ♥♠♦♣."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="suits"' not in html
    assert 'class="deck-fan"' in html
    for card in ("acq/acq_1.png", "couples/couples_1.png",
                 "sex/questions.png", "prov/prov.png"):
        assert card in html
