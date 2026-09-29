"""The Mini App draws on the same card PNGs the bot composites.

Serving them rather than re-drawing them in CSS is the whole point: it makes
"the same card" a fact instead of a resemblance. If the mount disappears,
every card in the Mini App silently loses its art and keeps its text.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vechnost_bot.payments.web import app

INDEX = Path(__file__).parent.parent / "webapp" / "index.html"

CARDS = [
    "acq/acq_1.png",
    "acq/acq_2.png",
    "acq/acq_3.png",
    "couples/couples_1.png",
    "couples/couples_2.png",
    "couples/couples_3.png",
    "sex/sex.png",
    "prov/prov.png",
    "library.png",
    "card_back.png",
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
    # Vacuous as a traversal test, kept as documentation of why: httpx
    # normalises the literal ".." away client-side, so the server only ever
    # sees GET /vechnost.db — a route that does not exist. The test that
    # actually reaches StaticFiles' traversal guard is the next one.
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


def _max_age(cache_control: str) -> int:
    match = re.search(r"max-age=(\d+)", cache_control)
    return int(match.group(1)) if match else 0


def test_the_page_goes_out_compressed_and_is_always_revalidated(client):
    """index.html is 211 KB of text and went out as it was, with no
    Cache-Control at all. Compressed it is about 60 KB; and it must be
    revalidated on every launch, or a deploy would not reach the phones
    that already have it."""
    with client.stream("GET", "/app/", headers={"Accept-Encoding": "gzip"}) as res:
        raw = b"".join(res.iter_raw())
        headers = res.headers
    assert res.status_code == 200
    assert headers["content-encoding"] == "gzip"
    assert len(raw) < 100_000, f"{len(raw)} bytes on the wire"
    assert "accept-encoding" in headers["vary"].lower()
    assert headers["cache-control"] == "no-cache"
    # The security headers are set inside the compression, not lost to it.
    assert headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors" in headers["content-security-policy"]
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    # A revalidation that comes back 304 says the same about caching.
    again = client.get("/app/", headers={"If-None-Match": headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "no-cache"


def test_fonts_and_card_art_are_kept_by_the_browser(client):
    """Twenty requests for the same fonts and PNGs on every launch, each
    answered only by an ETag, stood between a tap and the home screen."""
    font = client.get("/app/fonts/inter-400.woff2", headers={"Accept-Encoding": "gzip"})
    assert font.status_code == 200
    assert "public" in font.headers["cache-control"]
    assert _max_age(font.headers["cache-control"]) >= 30 * 86400
    # woff2 and PNG are compressed already; gzip would only cost CPU.
    assert "content-encoding" not in font.headers
    art = client.get("/assets/backgrounds/library.png", headers={"Accept-Encoding": "gzip"})
    assert art.status_code == 200
    assert "public" in art.headers["cache-control"]
    assert _max_age(art.headers["cache-control"]) >= 86400
    assert "content-encoding" not in art.headers
    again = client.get(
        "/assets/backgrounds/library.png", headers={"If-None-Match": art.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.headers["cache-control"] == art.headers["cache-control"]


def test_the_api_is_compressed_and_a_tiny_answer_is_not(client):
    questions = client.get("/api/questions", headers={"Accept-Encoding": "gzip"})
    assert questions.status_code == 200
    assert questions.headers.get("content-encoding") == "gzip"
    health = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in health.headers


def test_the_mini_app_points_at_the_real_card_art():
    html = INDEX.read_text(encoding="utf-8")
    assert "/assets/backgrounds/" in html
    assert "card_back.png" in html


def test_the_mini_app_no_longer_ships_the_old_typography():
    """Montserrat and Georgia are gone; the page is set in the brand's Inter
    and Lora. Forum, the face of the cards' V and Λ, was declared too and
    set nothing on the page (audit D-41): it is the card generator's."""
    html = INDEX.read_text(encoding="utf-8")
    assert "Montserrat" not in html
    assert "Georgia" not in html
    declared = set(re.findall(r"@font-face \{ font-family: '([^']+)'", html))
    assert declared == {"Inter", "Lora"}, declared


def test_the_mini_app_suits_match_the_printed_cards():
    """acq ♥, couples ♠, sex ♣, prov ♦.

    The suit is printed into the art, so the Mini App cannot get it wrong by
    naming the wrong character — it can only get it wrong by pointing a theme
    at another deck's face. CARD_ART is where that happens, and it is the
    mapping the app actually reads; the `SUITS` constant this test used to
    assert against fed nothing at all.
    """
    html = INDEX.read_text(encoding="utf-8")
    art = html.split("const CARD_ART = {", 1)[1].split("\n  };", 1)[0]
    for theme, folder in (
        ("Acquaintance", "acq"),
        ("For Couples", "couples"),
        ("Sex", "sex"),
        ("Provocation", "prov"),
    ):
        line = next(row for row in art.splitlines() if row.lstrip().startswith(f"'{theme}'"))
        faces = re.findall(r"'([a-z_]+)/[a-z_0-9]+\.png'", line)
        assert faces, f"{theme} names no card face"
        assert set(faces) == {folder}, f"{theme} wears {set(faces)}, not {folder}"


def test_every_deck_face_the_mini_app_names_is_a_file_that_exists():
    """CARD_ART must not drift from the PNGs the server actually serves."""
    html = INDEX.read_text(encoding="utf-8")
    backgrounds = Path(__file__).parent.parent / "assets" / "backgrounds"
    named = set(re.findall(r"'((?:acq|couples|sex|prov)/[a-z_0-9]+\.png)'", html))
    assert named == {c for c in CARDS if "/" in c}
    for rel in named:
        assert (backgrounds / rel).is_file()


def test_the_sex_deck_has_one_face_for_questions_and_tasks():
    """D-42: the art was one picture under three names. The deck is keyed
    by 'deck' now, as the bot's backgrounds.yml keys it by its default."""
    html = INDEX.read_text(encoding="utf-8")
    assert "'Sex':          { by: 'deck',  faces: { deck: 'sex/sex.png' } }" in html


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
    # #stage is touch-action: pan-y (see the test below), and this zone
    # declares its own so a nested scroller keeps the vertical pan that
    # scrolls the text on a touch screen.
    assert "touch-action" in q_zone
    # The size follows the card's width (17px on the smallest phones, 22px
    # from a 340px card up) and nothing else: no class shrinks it.
    q_text = _css_block(html, ".q-text")
    assert "font-size: var(--fs-card)" in q_text
    assert "--fs-card: clamp(17px, calc(var(--card-w) * 22 / 340), 22px);" in html


def test_the_card_and_its_text_band_scale_from_one_width():
    """D-04: the card's shape is fixed and every length on its face is a
    fraction of its width. A px margin inside a card whose box followed the
    stage is what left a 147px band on a 320x568 phone. The stage, not the
    card, is the size container: the card sits in the 3D flip."""
    html = INDEX.read_text(encoding="utf-8")
    for stage in ("#stage", "#libStage"):
        assert "container-type: size" in _css_block(html, stage)
    card = _css_block(html, ".card")
    assert "--card-w: min(100cqw, 100cqh * 340 / 470, var(--card-max-w));" in card
    assert "height: calc(var(--card-w) * 470 / 340);" in card
    assert "container-type" not in card
    front = _css_block(html, ".card .front")
    assert "padding: calc(var(--card-w) * 103 / 340) calc(var(--card-w) * 41 / 340);" in front
    declarations = re.sub(r"/\*.*?\*/", "", front, flags=re.S)
    assert "103px" not in declarations and "41px" not in declarations


def test_the_fade_marks_only_an_edge_that_actually_hides_something():
    """A fade that is always on dims the first line of an unscrolled card and
    the last line at the end — the rendering fault it exists to prevent."""
    html = INDEX.read_text(encoding="utf-8")
    assert ".card .front.cut-top::before {" in html
    assert ".card .front.cut-bottom::after {" in html
    assert "function markZoneEdges" in html
    # Global hooks, so a deck that does not know about them still gets it.
    assert "MutationObserver(refreshZoneEdges)" in html


def test_the_fade_never_masks_the_scroller_itself():
    """The fade is an overlay on the face, and must stay one. It replaced a
    mask on .q-zone, taken off when long cards would not scroll under a
    finger; the back face turned out to be the cause, and neither engine
    drops a masked scroller from its hit test today (audit H-02). So real
    input no longer catches a mask here: this check and the browser suite's
    computed-style probe are what hold the rule."""
    html = INDEX.read_text(encoding="utf-8")
    assert "mask-image" not in _css_block(html, ".q-zone")
    fade = _css_block(html, ".card .front::before,\n  .card .front::after")
    assert "pointer-events: none" in fade


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


def _library_js(html: str) -> str:
    """The Library's slice of the page script, deck controller included."""
    body = html.split("/* ---------------- library ---------------- */", 1)[1]
    return body.split("/* ---------------- compatibility test ---------------- */", 1)[0]


def test_the_library_no_longer_renders_bare_lists():
    html = INDEX.read_text(encoding="utf-8")
    # Scoped: an <ol> elsewhere on the page (a translation string, say) is not
    # this test's business, and banning it page-wide only sets a trap.
    assert "<ol>" not in _library_js(html)
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
    the deck itself must end on the prompt rather than just stopping. Both
    deck builders have to append it — the practice one and the category one."""
    html = INDEX.read_text(encoding="utf-8")
    assert "function libLockCard(" in html
    for fn in ("function libItems(", "function openLibCategory("):
        assert "libLockCard(" in html.split(fn)[1].split("\n  }")[0]


def test_both_decks_lay_their_cards_out_through_one_builder():
    """Two copies of the stage layout means two places to tune the animation,
    and one of them silently drifts."""
    html = INDEX.read_text(encoding="utf-8")
    assert html.count("className = 'card under'") == 1
    assert html.count("classList.add('faced')") == 1
    for fn in ("function renderStage(", "function renderLibStage("):
        assert "buildStage(" in html.split(fn)[1].split("\n  }")[0]


def test_a_card_that_flies_out_lands_in_the_deck_that_launched_it():
    """flyOut's callback runs 300ms later — long enough to leave the deck.
    Reading drag.onAdvance/COOP.active at landing time drove whatever screen
    the user went to: paging the Library stepped the saved game position."""
    html = INDEX.read_text(encoding="utf-8")
    fly = html.split("function flyOut(")[1].split("\n  }")[0]
    before, after = fly.split("setTimeout(", 1)
    # Captured on the way in...
    assert "drag.onAdvance" in before
    assert "COOP.active" in before
    # ...and not re-read on the way out.
    assert "drag.onAdvance" not in after
    assert "COOP.active" not in after
    # Left the deck mid-flight: step nothing.
    assert "classList.contains('active')" in after


def test_a_second_deck_on_the_same_screen_does_not_inherit_the_first_ones_timer():
    """The screen check above cannot tell two decks apart when they share an
    element: every Library deck is #libDeck, and solo and couple mode are both
    #deck. Leaving one Library deck for another inside the 300ms animation
    stepped the new deck by one; coop -> home -> a solo deck inside it ran
    coopAdvanceAfterFly with no room and left a blank stage that no longer
    responded. A generation counter is what distinguishes them."""
    html = INDEX.read_text(encoding="utf-8")
    # Every way onto a stage stamps a new generation...
    for fn in ("function enterDeck(", "function enterCoopDeck(", "function libDeckOpen("):
        assert "deckGen++" in html.split(fn)[1].split("\n  }")[0], fn
    fly = html.split("function flyOut(")[1].split("\n  }")[0]
    before, after = fly.split("setTimeout(", 1)
    # ...flyOut captures it with the rest of what it owns...
    assert "= deckGen" in before
    # ...and the landing stands down if it has moved, before anything else.
    assert "deckGen" in after
    assert after.index("deckGen") < after.index("classList.contains('active')")


def test_the_mini_app_ships_one_language():
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="lang-row"' not in html
    assert 'data-lang="en"' not in html
    assert 'data-lang="cs"' not in html
    assert "Pick a theme" not in html  # the English dictionary is gone
    assert "Vyber téma" not in html  # and the Czech one


def test_the_home_screen_shows_decks_not_typographic_suits():
    """The first thing the Mini App shows should be the game, not ♥♠♦♣."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="suits"' not in html
    assert 'class="deck-fan"' in html
    for card in ("acq/acq_1.png", "couples/couples_1.png", "sex/sex.png", "prov/prov.png"):
        assert card in html


def test_every_fan_card_wears_its_own_suit_as_a_centre_pip():
    """The corner mark on the deck art is ~6px at 72x108 and reads as a smudge.

    So each fan card layers its suit's own emblem over the card, centred, the
    way an Ace carries a centre pip. Pairing matters: a card showing another
    deck's suit would be worse than showing none, so this checks each emblem
    against the card it belongs to rather than merely counting four of them.
    The card is the deck's hand-drawn art, not the printed face: the tile is
    the art's 2:3, and the 4:5 face would be cropped at its sides here.
    """
    html = INDEX.read_text(encoding="utf-8")
    for suit, card in (
        ("hearts", "acq/acq_1.png"),
        ("spades", "couples/couples_1.png"),
        ("clubs", "sex/sex.png"),
        ("diamonds", "prov/prov.png"),
    ):
        pair = f"url(/assets/suits/{suit}.png),url(/assets/deck_art/{card})"
        assert pair in html, pair
        assert (INDEX.parent.parent / "assets" / "deck_art" / card).exists(), card


def test_no_screen_still_asks_for_a_typed_code():
    """Invites are links now, at all three doors.

    The three features drew six-character codes from one alphabet, so a code
    entered at the wrong door failed confusingly, and a mistyped character
    just refused the partner. A link cannot be entered at the wrong door.
    """
    html = INDEX.read_text(encoding="utf-8")
    for field in ("coopCodeInput", "compatCodeInput", "s69CodeInput"):
        assert field not in html, field
    assert 'class="coop-input"' not in html
    for button in ("btnCoopJoin", "btnCompatJoin", "btnS69Join"):
        assert button not in html, button


def test_the_invite_link_comes_from_the_server():
    """Only the server knows whether this deployment has a Mini App short
    name, and so which of the two link shapes actually works."""
    html = INDEX.read_text(encoding="utf-8")
    assert "invite_url" in html
    assert "showInviteLink" in html
    # No client-side link building: a hand-rolled t.me/<bot>?start=... would
    # go stale the moment a short name is configured. (The two shapes are
    # named in the comments that explain the boot path; that is not code.)
    code = "\n".join(line for line in html.splitlines() if not line.lstrip().startswith("//"))
    assert "?start=" not in code
    assert "?startapp=" not in code


def test_a_link_arriving_from_either_shape_lands_on_the_same_screen():
    """`startapp` hands the payload to the page; the bot's button spells it
    into the query string. Both have to reach the same join."""
    html = INDEX.read_text(encoding="utf-8")
    boot = html.split("function bootTarget(")[1].split("\n  }")[0]
    assert "initDataUnsafe" in boot and "start_param" in boot
    assert "tgWebAppStartParam" in boot
    assert "screen" in boot and "code" in boot
    for kind in ("s69:", "cmp:", "duo:"):
        assert kind in html, kind


def test_the_home_screen_carries_the_masterclass_and_hides_the_rest():
    """Five titles of prose on the first screen drowned out the four things
    a couple open the app to do. They live behind «Практики» now."""
    html = INDEX.read_text(encoding="utf-8")
    assert "const HOME_MODULES = ['nude_guide']" in html
    assert "btnPractices" in html
    assert "Интерактивная игра 69 ступеней" in html
    assert "Территория наслаждения" not in html


def test_an_overlay_taller_than_the_phone_can_be_scrolled():
    """The 69 finale is two choices with a paragraph each. Centred with
    justify-content it pushed its own head above the scroll origin and left
    the buttons under it unreachable."""
    html = INDEX.read_text(encoding="utf-8")
    block = html.split("  .overlay {")[1].split("}")[0]
    assert "overflow-y: auto" in block
    assert "justify-content: center" not in block
    assert ".overlay > :first-child { margin-top: auto; }" in html


def test_a_long_compatibility_question_scrolls_instead_of_pushing_the_answers_off():
    html = INDEX.read_text(encoding="utf-8")
    block = html.split("  #compatQuestion{")[1].split("}")[0]
    assert "overflow-y:auto" in block
    assert "min-height:0" in block


def test_every_guide_picture_says_its_view_and_its_light():
    """At 136px a photograph shows a body turned away and a body in profile
    nearly alike, so every picture has a caption, and a pose's caption says
    the view and where the light stands outright."""
    from vechnost_bot.i18n import Language
    from vechnost_bot.library import load_guide

    html = INDEX.read_text(encoding="utf-8")
    captions = dict(
        re.findall(
            r"'([a-z0-9-]+)': '([^']+)'",
            html.split("const ART_CAPTIONS = {")[1].split("\n  };")[0],
        )
    )
    for step in load_guide("nude_guide", Language.RUSSIAN):
        for item in step.items:
            assert item.art in captions, item.art
            if step.id in ("her", "him"):
                caption = captions[item.art]
                assert caption.startswith(("вид ", "кадр ")) and "свет" in caption, caption


def test_guide_pictures_are_fetched_with_the_reader_never_linked():
    """The pose pictures are paid and 18+ like the words beside them, so the
    page asks the Library API for each with the reader's initData; a link to
    a file anyone can open would be the paywall's back door."""
    html = INDEX.read_text(encoding="utf-8")
    loader = html.split("async function loadArt(")[1].split("\n  }")[0]
    assert "'/api/library/' + moduleId + '/art/'" in loader
    assert "Authorization" in loader and "libNsfwParam()" in loader
    assert ".webp" not in html and "library/art" not in html


def test_the_compat_result_reads_in_the_agreed_order():
    """Team spheres first, then the questions to discuss, then the three
    zones from strong to critical. The flat «По всем сферам» list and the
    separate attention block are gone — every sphere now sits under the
    zone it landed in, with the attention framing riding on its card."""
    html = INDEX.read_text(encoding="utf-8")
    body = html.split("function renderCompatResult(")[1].split("\n  }")[0]
    # The last template in the function is the assembled screen; the earlier
    # `return \`` belongs to the zoneSection helper.
    ret = body.split("return `")[-1]
    order = [
        ret.index("compatStrengths"),
        ret.index("${discuss}"),
        ret.index("${zoneSection('strength')}"),
        ret.index("${zoneSection('growth')}"),
        ret.index("${crisis}"),
    ]
    assert order == sorted(order)
    assert "compatAll" not in html
    assert "compatAttention" not in html


def test_a_divergent_question_number_opens_its_text_on_a_tap():
    """«Обсудите вопросы №12» is only actionable with question 12 under it.
    The number is a <details> summary, so the text opens on a tap with no
    script to break, and the texts come with the result payload."""
    html = INDEX.read_text(encoding="utf-8")
    fn = html.split("function compatQuestionsHTML(")[1].split("\n  }")[0]
    assert "<details" in fn and "<summary" in fn
    body = html.split("function renderCompatResult(")[1].split("\n  }")[0]
    assert body.count("compatQuestionsHTML(") >= 2  # sphere cards and the discuss block
    assert "r.questions" in body


def test_no_board_square_shows_what_lies_ahead():
    """The «69 ступеней» map is a picture, not a row of buttons: a tap on a
    square used to open its task, and a square the piece had not reached
    read out what it would ask before it was dealt. No square takes a tap,
    the overlay that showed one is gone, and the map is drawn without
    reading any text (the board payload carries none: test_steps69)."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="s69CellInfo"' not in html
    assert "showS69CellInfo" not in html
    build = html.split("function buildS69Map(")[1].split("\n  }")[0]
    assert "onclick" not in build and "addEventListener" not in build
    assert ".text" not in build
    assert 'id="s69Map" role="img"' in html


def test_the_board_draws_its_portals():
    """A ladder is a Cupid's arrow from its square to the one it carries the
    piece to, a snake a serpent with its head on its square and its tail on
    the one it drops the piece to - drawn from each portal cell's `to`, over
    the squares, with a lotus under them, and the piece rides the drawing."""
    html = INDEX.read_text(encoding="utf-8")
    build = html.split("function buildS69Map(")[1].split("\n  }")[0]
    assert "s69ArrowSVG(c)" in build and "s69SnakeSVG(c)" in build
    assert "s69LotusSVG(" in build
    arrow = html.split("function s69ArrowSVG(")[1].split("\n  }")[0]
    assert "s69Point(cell.id)" in arrow and "s69Point(cell.to)" in arrow
    assert "s69-heart" in arrow and "s69-feather" in arrow
    spine = html.split("function s69Spine(")[1].split("\n  }")[0]
    assert "s69Point(from)" in spine and "s69Point(to)" in spine
    snake = html.split("function s69SnakeSVG(")[1].split("\n  }")[0]
    assert "s69Spine(cell.id, cell.to)" in snake and "s69-tongue" in snake
    fly = html.split("function flyS69Piece(")[1].split("\n  }")[0]
    assert "s69Route(" in fly and "REDUCED_MOTION" in fly


# Emoji and pictographs, the four card suits aside: those are the board's.
EMOJI = re.compile(
    "[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u265f\u2667-\u27bf\u2b00-\u2bff\ufe0f\u200d]"
)


def test_the_board_speaks_in_suits():
    """No emoji on «69 ступеней» (CLAUDE.md; audit D-39). Three were left: a
    map on the button that folds the map, fire over the finale and fireworks
    over its end. The button is a drawing, both finales show the pair's two
    suits, and the turn chip leads with the mover's suit instead of a
    sparkle. What the board says is its screens, its overlays, its copy and
    the code that writes into them; the home screen's button and the
    invitation a player sends are not on the board."""
    html = INDEX.read_text(encoding="utf-8")
    parts = {
        f"#{sid}": html.split(f'<section class="screen" id="{sid}">')[1].split("</section>")[0]
        for sid in ("s69", "s69Invite", "s69Board")
    }
    for oid in ("s69Finale", "s69Done"):
        parts[f"#{oid}"] = html.split(f'<div class="overlay" id="{oid}"')[1].split("\n  </div>")[0]
    i18n = html.split("const I18N = {", 1)[1].split("\n  };", 1)[0]
    for key, text in re.findall(r"\b(s69\w*):\s*('[^']*'|\{[^}]*\})", i18n):
        if key not in ("s69Btn", "s69InviteMsg"):
            parts[f"I18N.{key}"] = text
    parts["the board's code"] = html.split("const S69_SUITS = {")[1].split(
        "/* ---------------- boot"
    )[0]
    found = {where: sorted(set(EMOJI.findall(text))) for where, text in parts.items()}
    assert not {where: chars for where, chars in found.items() if chars}, found
    assert "<svg" in parts["#s69Board"].split('id="s69MapToggle"')[1].split("</button>")[0]
    for oid in ("s69FinaleSuits", "s69DoneSuits"):
        assert f"$('{oid}').innerHTML = s69PairHTML(st)" in html, oid


def test_the_fade_follows_the_text_s_size_not_only_its_events():
    """A late font or a stage that settles after the scroll re-flows a card's
    text with no scroll, mutation or resize event; the flags now follow the
    zone's and the text's size (tests/e2e/browser/test_touch.py shows it)."""
    html = INDEX.read_text(encoding="utf-8")
    refresh = html.split("function refreshZoneEdges() {")[1].split("\n  }\n")[0]
    assert "zoneWatch.observe(z)" in refresh
    assert "zoneWatch.unobserve(z)" in refresh  # a thrown-away card is let go
    assert "new ResizeObserver(" in html


def test_the_back_of_the_card_never_takes_a_touch():
    """The back face was eating the scroll gesture.

    `backface-visibility: hidden` hides the back from the eye, but not from
    the compositor's touch hit test: both faces are clip layers and the back
    is later in the DOM, so a finger in the middle of a card landed on it —
    and behind the back there is no scroller. Long questions were readable
    only by script: `elementFromPoint` returns `.q-text` and disagrees with
    what a real touch does, which is why this survived a browser check.

    Verified with real touch input (CDP `Input.dispatchTouchEvent`) in a
    mobile Chromium: without the rule the zone's scrollTop stays 0; with it
    the card scrolls its full range and the swipe still works.
    """
    html = INDEX.read_text(encoding="utf-8")
    back = html.split("  .card .back {")[1].split("}")[0]
    assert "pointer-events: none" in back


def test_the_turn_chip_keeps_a_refusal_s_flash_through_a_poll():
    """The room is polled every 2.5 s and each poll redraws the turn chip.

    It used to assign `className`, which dropped the `pulse` a refused tap
    had just put on: the flash was cut short whenever a poll landed within
    its 0.7 s, and a browser test waiting for the class timed out on WebKit.
    The HUD toggles the one class it owns; the refusal's class comes off at
    `animationend`.
    """
    html = INDEX.read_text(encoding="utf-8")
    hud = html.split("function updateCoopHud() {")[1].split("\n  }\n")[0]
    assert not re.search(r"\.className\s*=", hud)
    assert "classList.toggle('turn-you'" in hud
    refuse = html.split("function refuseTurn() {")[1].split("\n  }\n")[0]
    assert "'animationend'" in refuse


def test_the_paywall_leaves_a_live_card_on_the_stage():
    """Closing the paywall must land on a working deck, not a frozen one.

    `finishDeck`'s paywall branch used to return without rebuilding the
    stage: the last free card had already flown off, `deckDirty` stayed
    set, and closing the paywall left a dead screen where nothing —
    buttons, swipes, even the paywall itself — responded until the user
    left the deck. Reproduced with a real unpaid session in Chromium; the
    rebuild is what makes the last free card come back and stay swipeable.
    """
    html = INDEX.read_text(encoding="utf-8")
    branch = html.split("if (!ACCESS.paid && full > freeN) {")[1].split("}")[0]
    assert "renderStage" in branch
    assert branch.index("renderStage") < branch.index("showPaywall")


def test_a_screen_switch_dismisses_overlays():
    """Back must not leave «Колода пройдена!» floating over the home screen.

    Overlays are absolutely positioned siblings of the screens, so they
    survive `show()` unless it clears them — and the finished-deck banner,
    the paywall and the 18+ gate all did, because only `leaveS69` cleaned
    up after itself. The rule now lives in `show()`, once, for all of them.
    """
    html = INDEX.read_text(encoding="utf-8")
    body = html.split("function show(id) {")[1].split("\n  }")[0]
    assert ".overlay.show" in body


def test_the_compat_resume_offer_is_rewired_on_every_visit():
    """The «Продолжить тест» button must never outlive the code it offers.

    Its text and click handler used to be wired only from the home-screen
    button, so after a delete or a second test every other route back to
    the entry screen showed a button that 404s forever.
    """
    html = INDEX.read_text(encoding="utf-8")
    body = html.split("function show(id) {")[1].split("\n  }")[0]
    assert "refreshCompatResume" in body
    assert "function refreshCompatResume()" in html


def test_the_pollers_keep_one_request_in_flight():
    """A bare interval stacks requests on a slow link.

    Answers landing out of order repainted newer state with older — in «69
    ступеней» the piece visibly jumped backwards and the portal toast fired
    twice. The three pollers now share one loop that schedules the next
    request only after the previous one has answered, so there is never a
    second in flight by construction.
    """
    html = INDEX.read_text(encoding="utf-8")
    loop = html.split("function startPoll(")[1].split("\n  }\n")[0]
    assert "await fetchState()" in loop
    assert "setTimeout(tick, delay)" in loop, "the next tick is scheduled after the answer"
    assert "setInterval(" not in html
    for fn in ("function startCoopPoll", "function startCompatPoll", "function startS69Poll"):
        body = html.split(fn)[1].split("\n  }")[0]
        assert "startPoll(" in body, f"{fn} runs its own loop again"


def test_the_finale_overlay_is_not_rebuilt_under_a_tap():
    """Every poll tick lands in showS69Finale while the pair read the text.

    Rebuilding the open overlay reset its scroll and could swallow the tap
    that chooses the finale; once shown, it stays as built.
    """
    html = INDEX.read_text(encoding="utf-8")
    body = html.split("function showS69Finale(st) {")[1].split("\n  }")[0]
    assert "contains('show')) return" in body


def _root_block(html: str) -> str:
    """The declarations of the page's :root rule: the design tokens."""
    return html.split("  :root {", 1)[1].split("\n  }", 1)[0]


def test_the_old_custom_property_names_are_aliases_of_the_tokens():
    """The token block is the one place a value is spelled. The names the
    rules were written against stay, pointing at it, so a colour changed in
    the palette reaches every rule that still says --ink or --card-bg; and
    the two that nothing ever read are gone."""
    html = INDEX.read_text(encoding="utf-8")
    root = _root_block(html)
    for alias, token in (
        ("--ink", "--c-ink"),
        ("--card-bg", "--card-ground"),
        ("--text-on-dark", "--text-1"),
        ("--muted-on-dark", "--text-2"),
        ("--radius-card", "--r-card"),
    ):
        assert f"{alias}: var({token});" in root, alias
    assert re.search(r"--card-ground:\s+var\(--c-blush-50\)", root)
    assert re.search(r"--c-blush-50:\s+#FFE5FA", root), "generate_card_assets.PALE"
    assert "--shell-1" not in html
    assert "--font-emblem" not in html


def test_every_custom_property_the_page_reads_is_declared():
    """A misspelt token is not an error in CSS: var() of an undeclared name
    quietly falls back to the property's initial value, so a colour turns
    black or a gap turns zero and nothing says why."""
    html = INDEX.read_text(encoding="utf-8")
    declared = set(re.findall(r"(--[\w-]+)\s*:", html))
    used = set(re.findall(r"var\((--[\w-]+)", html))
    # Telegram sets its own --tg-* on the document from telegram-web-app.js.
    missing = {name for name in used - declared if not name.startswith("--tg-")}
    assert not missing, missing


def test_every_weight_is_one_the_page_ships():
    """D-26: the page ships Inter at 400, 600 and 700 and Lora at 400, and a
    weight between them is not drawn. 800 came out as 700 and 500 as 400,
    while nine rules said otherwise; the weight tokens hold the three."""
    html = INDEX.read_text(encoding="utf-8")
    shipped = set(re.findall(r"font-family: 'Inter'; src: url\('fonts/inter-(\d{3})", html))
    assert shipped == {"400", "600", "700"}, shipped
    tokens = dict(re.findall(r"(--fw-[a-z]+):\s*(\d{3})", html))
    assert set(tokens.values()) == shipped, tokens
    allowed = shipped | {f"var({name})" for name in tokens} | {"inherit", "normal", "bold"}
    weights = {w.strip() for w in re.findall(r"font-weight:\s*([^;}\"']+)", html)}
    assert weights <= allowed, weights - allowed


def test_what_destroys_a_shared_thing_looks_dangerous():
    """D-38: deleting the test's answers and restarting the board wipe what
    two people share, and looked like every other quiet button."""
    html = INDEX.read_text(encoding="utf-8")
    for button in ("compatDeleteBtn", "btnS69Restart"):
        tag = html.split(f'id="{button}"', 1)[0].rsplit("<button", 1)[1]
        assert "btn-danger" in tag, button
    rule = re.search(r"\.btn\.btn-danger\s*\{([^}]*)\}", html)
    assert rule and "var(--danger)" in rule.group(1)


def test_a_transition_names_what_it_animates():
    """D-26: `transition: all` animates whatever the next change happens to
    be, layout included, and hides which property the rule meant."""
    html = INDEX.read_text(encoding="utf-8")
    assert not re.search(r"transition(-property)?:\s*all\b", html)


def test_a_phone_that_asks_for_less_motion_gets_no_confetti():
    """D-13: the CSS block stops the looping and travelling animations; the
    confetti is spawned from script, so the script asks too."""
    html = INDEX.read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in html
    body = html.split("function confetti() {", 1)[1]
    assert body.lstrip().startswith("if (REDUCED_MOTION) return;")
    # The fan does not float even once: the block's .01ms left each card a
    # float pending after its delay, drawn differently from one at rest.
    block = html.split("@media (prefers-reduced-motion: reduce) {", 1)[1].split("\n  }\n", 1)[0]
    assert ".deck-fan i { animation: none; }" in block


def test_a_scroll_asked_for_by_script_asks_about_motion_too():
    """D-13: the reduced-motion block sets scroll-behavior, which a
    `behavior: 'smooth'` passed from script overrides. The board's map
    travelled for half a second on a phone that asked for less motion; it
    no longer scrolls at all, and whatever scrolls from script next asks."""
    html = INDEX.read_text(encoding="utf-8")
    script = html.split("<script>", 1)[1]
    asked = re.findall(r"behavior\s*=\s*([^;]+);|[{,]\s*behavior:\s*([^,}]+)", script)
    values = [a or b for a, b in asked]
    for value in values:
        if "smooth" in value:
            assert "REDUCED_MOTION" in value, value


class _LastChild(HTMLParser):
    """The last element child of the element with this id, as (tag, attrs)."""

    VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }

    def __init__(self, container: str) -> None:
        super().__init__()
        self.container = container
        self.depth = 0  # 0 outside the container, 1 among its children
        self.last: tuple[str, dict[str, str | None]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth == 0:
            if dict(attrs).get("id") == self.container:
                self.depth = 1
            return
        if self.depth == 1:
            self.last = (tag, dict(attrs))
        if tag not in self.VOID:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag not in self.VOID:
            self.depth -= 1


def test_a_centred_column_ends_on_something_visible():
    """#home centres its column with margin-bottom:auto on :last-child, and
    :last-child counts a hidden element too. The gift button, kept at the
    end of #home with display:none, took the centring with it: the home
    screen sank to the bottom of every tall phone. What may be hidden is
    added and removed. (The theme and level lists start at the top since
    audit D-28, so there is nothing of theirs to sink.)"""
    html = INDEX.read_text(encoding="utf-8")
    assert "#home > :last-child" in html
    for container in ("home",):
        parser = _LastChild(container)
        parser.feed(html)
        if parser.last is None:
            continue  # filled from script
        tag, attrs = parser.last
        style = (attrs.get("style") or "").replace(" ", "")
        assert "display:none" not in style and "hidden" not in attrs, (container, tag, attrs)


def test_the_launch_preload_is_quiet():
    """D-16: the preload at launch shows no loader and says nothing; «Играть»
    waits for the same request with the loader up."""
    html = INDEX.read_text(encoding="utf-8")
    assert "loadData(true);" in html
    assert "\n  loadData();" not in html


def test_every_overlay_with_a_way_out_names_it_for_the_back_button():
    """D-06: Back closes the top overlay the way its own button would."""
    html = INDEX.read_text(encoding="utf-8")
    for button in ("nsfwNo", "s69DoneHome", "paywallClose", "btnToThemes"):
        tag = html.split(f'id="{button}"', 1)[1].split(">", 1)[0]
        assert "data-dismiss" in tag, button
