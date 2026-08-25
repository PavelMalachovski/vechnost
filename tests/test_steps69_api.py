"""«69 ступеней» over HTTP: turns, the paywall, and what each phone is told."""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot import steps69
from vechnost_bot.config import settings
from vechnost_bot.payments.web import app

ALICE = {"X-Guest-Id": "alice-device"}
BOB = {"X-Guest-Id": "bob-device"}
EVE = {"X-Guest-Id": "eve-device"}


@pytest.fixture
def client(tmp_path):
    """TestClient on a fresh temp SQLite DB, payments off."""
    db_path = tmp_path / "steps69.db"
    with (
        patch.object(settings, "database_url", f"sqlite:///{db_path}"),
        patch.object(settings, "enable_payment", False),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield TestClient(app)


def create(client, headers=ALICE, mode="duo"):
    response = client.post("/api/steps69", json={"mode": mode}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def started_game(client):
    """A duo game with both seats taken."""
    game = create(client)
    join = client.post(f"/api/steps69/{game['code']}/join", headers=BOB)
    assert join.status_code == 200, join.text
    return game["code"]


# ---------------------------------------------------------------------------
# Starting a game
# ---------------------------------------------------------------------------

def test_a_new_game_starts_on_cell_one(client):
    game = create(client)
    assert game["position"] == 1
    assert game["turns"] == 0
    assert game["finished"] is False
    assert game["cell"]["kind"] == "start"
    assert len(game["code"]) == 6


def test_the_creator_takes_the_first_seat(client):
    game = create(client)
    assert game["your_role"] == "creator"
    assert game["your_seat"] == 0
    assert game["started"] is False


def test_a_partner_joining_starts_the_game(client):
    game = create(client)
    joined = client.post(f"/api/steps69/{game['code']}/join", headers=BOB).json()
    assert joined["your_role"] == "guest"
    assert joined["started"] is True
    assert joined["players"]["guest"]


def test_a_third_player_cannot_take_a_seat(client):
    code = started_game(client)
    response = client.post(f"/api/steps69/{code}/join", headers=EVE)
    assert response.status_code == 409


def test_the_creator_may_reopen_their_own_game(client):
    code = started_game(client)
    response = client.post(f"/api/steps69/{code}/join", headers=ALICE)
    assert response.status_code == 200
    assert response.json()["your_role"] == "creator"


def test_joining_an_unknown_code_is_a_404(client):
    assert client.post("/api/steps69/ZZZZZZ/join", headers=BOB).status_code == 404


def test_a_solo_game_takes_no_guest(client):
    """One phone passed between partners has one seat by definition."""
    game = create(client, mode="solo")
    assert game["mode"] == "solo"
    assert game["started"] is True
    response = client.post(f"/api/steps69/{game['code']}/join", headers=BOB)
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Turns
# ---------------------------------------------------------------------------

def test_nobody_rolls_before_the_partner_arrives(client):
    game = create(client)
    response = client.post(f"/api/steps69/{game['code']}/roll", headers=ALICE)
    assert response.status_code == 409


def test_the_dice_are_blocked_for_whoever_is_not_on_turn(client):
    """The brief: «Кнопка Бросить кубик блокируется для одного, пока ходит другой»."""
    code = started_game(client)
    assert client.post(f"/api/steps69/{code}/roll", headers=BOB).status_code == 403
    assert client.post(f"/api/steps69/{code}/roll", headers=ALICE).status_code == 200
    assert client.post(f"/api/steps69/{code}/roll", headers=ALICE).status_code == 403


def test_the_turn_alternates(client):
    code = started_game(client)
    first = client.post(f"/api/steps69/{code}/roll", headers=ALICE).json()
    assert first["your_turn"] is False
    second = client.get(f"/api/steps69/{code}", headers=BOB).json()
    assert second["your_turn"] is True


def test_a_solo_game_needs_no_partner_to_roll(client):
    game = create(client, mode="solo")
    response = client.post(f"/api/steps69/{game['code']}/roll", headers=ALICE)
    assert response.status_code == 200
    assert response.json()["turns"] == 1


def test_a_roll_reports_where_the_piece_came_from(client):
    """A partner polling mid-animation must see the same move, not a piece
    that teleported."""
    code = started_game(client)
    rolled = client.post(f"/api/steps69/{code}/roll", headers=ALICE).json()
    last = rolled["last"]
    assert last["from"] == 1
    assert 1 <= last["roll"] <= 6
    assert last["landed"] == 1 + last["roll"]

    partner_view = client.get(f"/api/steps69/{code}", headers=BOB).json()
    assert partner_view["last"] == last
    assert partner_view["position"] == rolled["position"]


def test_a_stranger_can_neither_watch_nor_roll(client):
    code = started_game(client)
    assert client.get(f"/api/steps69/{code}", headers=EVE).status_code == 403
    assert client.post(f"/api/steps69/{code}/roll", headers=EVE).status_code == 403
    assert client.get(f"/api/steps69/{code}/board", headers=EVE).status_code == 403


# ---------------------------------------------------------------------------
# Portals
# ---------------------------------------------------------------------------

def test_a_ladder_moves_the_piece_the_moment_it_is_landed_on(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=3):  # 1 -> 4 -> 18
        rolled = client.post(f"/api/steps69/{code}/roll", headers=ALICE).json()
    assert rolled["last"]["landed"] == 4
    assert rolled["position"] == 18
    assert rolled["last"]["event"] == "ladder"
    assert rolled["last"]["message"]


def test_a_snake_drags_the_piece_back(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        client.post(f"/api/steps69/{code}/roll", headers=ALICE)   # 1 -> 7
        rolled = client.post(f"/api/steps69/{code}/roll", headers=BOB).json()  # 7 -> 13 -> 2
    assert rolled["last"]["landed"] == 13
    assert rolled["position"] == 2
    assert rolled["last"]["event"] == "snake"


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def test_only_the_player_who_rolled_reads_the_secret(client):
    """The brief: «Текст под спойлером должен быть уникальным для каждого игрока»."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=4):  # 1 -> 5, a secret
        mover = client.post(f"/api/steps69/{code}/roll", headers=ALICE).json()
    watcher = client.get(f"/api/steps69/{code}", headers=BOB).json()

    assert mover["cell"]["kind"] == "secret"
    assert mover["cell"]["secret"]
    assert mover["cell"]["partner"] is None
    assert watcher["cell"]["secret"] is None
    assert watcher["cell"]["partner"]


def test_the_partners_secret_never_reaches_the_wire(client):
    """Asserted on the raw body rather than a parsed field: a leak under an
    unexpected key would slip past a field-level check."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=4):
        client.post(f"/api/steps69/{code}/roll", headers=ALICE)

    secret_text = steps69.cell(5).secret
    watcher = client.get(f"/api/steps69/{code}", headers=BOB)
    assert secret_text not in watcher.text


def test_one_phone_shows_both_halves(client):
    game = create(client, mode="solo")
    with patch.object(steps69, "roll_dice", return_value=4):
        rolled = client.post(f"/api/steps69/{game['code']}/roll", headers=ALICE).json()
    assert rolled["cell"]["secret"] and rolled["cell"]["partner"]


# ---------------------------------------------------------------------------
# The Joker
# ---------------------------------------------------------------------------

def test_a_joker_deals_one_task_and_both_phones_see_the_same_one(client):
    """Two clients polling one game must agree on what was dealt, so the
    draw happens once on the server rather than per request."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        client.post(f"/api/steps69/{code}/roll", headers=ALICE)   # 1 -> 7
    with patch.object(steps69, "roll_dice", return_value=2):
        mover = client.post(f"/api/steps69/{code}/roll", headers=BOB).json()  # 7 -> 9

    watcher = client.get(f"/api/steps69/{code}", headers=ALICE).json()
    assert mover["cell"]["kind"] == "joker"
    assert mover["cell"]["joker"]["text"]
    assert watcher["cell"]["joker"] == mover["cell"]["joker"]

    # Polling again must not redraw.
    assert client.get(f"/api/steps69/{code}", headers=BOB).json()["cell"]["joker"] == mover["cell"]["joker"]


def test_the_joker_clears_when_the_piece_moves_on(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        client.post(f"/api/steps69/{code}/roll", headers=ALICE)   # 1 -> 7
    with patch.object(steps69, "roll_dice", return_value=2):
        joker = client.post(f"/api/steps69/{code}/roll", headers=BOB).json()  # 7 -> 9
    assert joker["cell"]["kind"] == "joker"
    assert joker["cell"]["joker"]

    with patch.object(steps69, "roll_dice", return_value=1):
        after = client.post(f"/api/steps69/{code}/roll", headers=ALICE).json()
    assert after["cell"]["kind"] != "joker"
    assert "joker" not in after["cell"]


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------

def test_the_board_is_legible_but_gives_nothing_away(client):
    code = started_game(client)
    board = client.get(f"/api/steps69/{code}/board", headers=BOB)
    assert board.status_code == 200
    payload = board.json()
    assert payload["size"] == 69
    assert len(payload["cells"]) == 69
    assert all(c["title"] for c in payload["cells"])

    body = board.text
    for c in steps69.load_cells():
        if c.secret:
            assert c.secret not in body, f"cell {c.id} secret leaked into the map"
        if c.text:
            assert c.text not in body, f"cell {c.id} instruction leaked into the map"


def test_the_map_carries_the_portal_arrows(client):
    code = started_game(client)
    cells = client.get(f"/api/steps69/{code}/board", headers=BOB).json()["cells"]
    by_id = {c["id"]: c for c in cells}
    assert by_id[4]["to"] == 18 and by_id[4]["kind"] == "ladder"
    assert by_id[13]["to"] == 2 and by_id[13]["kind"] == "snake"


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

def test_a_reaction_reaches_the_partner(client):
    code = started_game(client)
    sent = client.post(f"/api/steps69/{code}/react", json={"emoji": "🔥"}, headers=ALICE)
    assert sent.status_code == 200
    seen = client.get(f"/api/steps69/{code}", headers=BOB).json()["reactions"]
    assert seen[-1]["emoji"] == "🔥"
    assert seen[-1]["by"] == "creator"
    assert seen[-1]["seq"] == 1


def test_reaction_sequence_numbers_only_go_up(client):
    code = started_game(client)
    for _ in range(3):
        client.post(f"/api/steps69/{code}/react", json={"emoji": "❤️"}, headers=BOB)
    seqs = [r["seq"] for r in client.get(f"/api/steps69/{code}", headers=BOB).json()["reactions"]]
    assert seqs == sorted(set(seqs)) == [1, 2, 3]


def test_only_the_palette_is_accepted(client):
    """Whatever lands here is stored and rendered on the other phone."""
    code = started_game(client)
    response = client.post(
        f"/api/steps69/{code}/react", json={"emoji": "💩"}, headers=ALICE
    )
    assert response.status_code == 400


def test_the_reaction_tail_stays_short(client):
    from vechnost_bot.payments.steps69_api import REACTION_TAIL

    code = started_game(client)
    for _ in range(REACTION_TAIL + 5):
        client.post(f"/api/steps69/{code}/react", json={"emoji": "😈"}, headers=ALICE)
    tail = client.get(f"/api/steps69/{code}", headers=ALICE).json()["reactions"]
    assert len(tail) == REACTION_TAIL


# ---------------------------------------------------------------------------
# The finale
# ---------------------------------------------------------------------------

def test_the_dice_are_dead_on_sixty_nine(client):
    """The brief: cell 69 blocks the dice for the rest of the session."""
    code = started_game(client)
    _walk_to_69(client, code)
    state = client.get(f"/api/steps69/{code}", headers=ALICE).json()
    assert state["position"] == 69
    assert state["your_turn"] is False

    for headers in (ALICE, BOB):
        assert client.post(f"/api/steps69/{code}/roll", headers=headers).status_code == 409


def test_the_finale_offers_both_endings(client):
    code = started_game(client)
    _walk_to_69(client, code)
    cell = client.get(f"/api/steps69/{code}", headers=ALICE).json()["cell"]
    assert cell["kind"] == "final"
    assert {c["id"] for c in cell["finale"]["choices"]} == {"sync", "taking_turns"}


def test_choosing_a_finale_ends_the_game(client):
    code = started_game(client)
    _walk_to_69(client, code)
    done = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE
    ).json()
    assert done["finished"] is True
    assert done["finale_choice"] == "sync"


def test_the_first_choice_stands_when_both_partners_tap(client):
    code = started_game(client)
    _walk_to_69(client, code)
    client.post(f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE)
    second = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "taking_turns"}, headers=BOB
    )
    assert second.status_code == 409
    state = client.get(f"/api/steps69/{code}", headers=BOB).json()
    assert state["finale_choice"] == "sync"


def test_an_unknown_finale_is_refused(client):
    code = started_game(client)
    _walk_to_69(client, code)
    response = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "whatever"}, headers=ALICE
    )
    assert response.status_code == 404


def test_the_finale_cannot_be_chosen_early(client):
    code = started_game(client)
    response = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Coming back later
# ---------------------------------------------------------------------------

def test_a_game_in_play_can_be_found_again(client):
    """The piece waiting on cell 45 is the whole premise of the resume push."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=2):
        client.post(f"/api/steps69/{code}/roll", headers=ALICE)

    mine = client.get("/api/steps69/mine", headers=BOB)
    assert mine.status_code == 200
    assert mine.json()["code"] == code


def test_a_finished_game_is_not_offered_to_continue(client):
    code = started_game(client)
    _walk_to_69(client, code)
    client.post(f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE)
    assert client.get("/api/steps69/mine", headers=ALICE).status_code == 404


def test_either_partner_can_erase_the_game(client):
    code = started_game(client)
    assert client.delete(f"/api/steps69/{code}", headers=BOB).status_code == 200
    assert client.get(f"/api/steps69/{code}", headers=ALICE).status_code == 404


def test_a_stranger_cannot_erase_the_game(client):
    code = started_game(client)
    assert client.delete(f"/api/steps69/{code}", headers=EVE).status_code == 403
    assert client.get(f"/api/steps69/{code}", headers=ALICE).status_code == 200


# ---------------------------------------------------------------------------
# The paywall
# ---------------------------------------------------------------------------

def test_an_unpaid_visitor_cannot_start_a_game(client):
    """The game is paid outright: there is no free prefix to trim."""
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.steps69_api.validate_init_data",
            return_value={"user": {"id": 777, "first_name": "Unpaid"}},
        ),
        patch(
            "vechnost_bot.payments.steps69_api.user_has_access", return_value=False
        ),
    ):
        response = client.post(
            "/api/steps69", json={"mode": "duo"}, headers={"Authorization": "tma x"}
        )
    assert response.status_code == 402


def test_a_paid_user_can_start_a_game(client):
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.steps69_api.validate_init_data",
            return_value={"user": {"id": 778, "first_name": "Paid"}},
        ),
        patch("vechnost_bot.payments.steps69_api.user_has_access", return_value=True),
    ):
        response = client.post(
            "/api/steps69", json={"mode": "duo"}, headers={"Authorization": "tma x"}
        )
    assert response.status_code == 200


def test_the_guest_plays_on_the_creators_payment(client):
    """One payment covers both partners, exactly as a room does."""
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.steps69_api.validate_init_data",
            side_effect=[
                {"user": {"id": 900, "first_name": "Payer"}},
                {"user": {"id": 901, "first_name": "Guest"}},
                {"user": {"id": 901, "first_name": "Guest"}},
            ],
        ),
        patch(
            "vechnost_bot.payments.steps69_api.user_has_access",
            side_effect=[True],
        ),
    ):
        created = client.post(
            "/api/steps69", json={"mode": "duo"}, headers={"Authorization": "tma payer"}
        )
        assert created.status_code == 200
        code = created.json()["code"]

        joined = client.post(
            f"/api/steps69/{code}/join", headers={"Authorization": "tma guest"}
        )
        assert joined.status_code == 200

        board = client.get(
            f"/api/steps69/{code}/board", headers={"Authorization": "tma guest"}
        )
        assert board.status_code == 200


def test_an_anonymous_caller_is_refused_when_payments_are_on(client):
    with patch.object(settings, "enable_payment", True):
        assert client.post("/api/steps69", json={"mode": "duo"}).status_code == 401
        assert client.post("/api/steps69", json={"mode": "duo"}, headers=ALICE).status_code == 401


# ---------------------------------------------------------------------------

def _walk_to_69(client, code):
    """Roll the pair to the last square, whoever's turn it happens to be."""
    for _ in range(40):
        state = client.get(f"/api/steps69/{code}", headers=ALICE).json()
        if state["position"] >= steps69.BOARD_SIZE:
            return
        holder = ALICE if state["turn"] == 0 else BOB
        with patch.object(steps69, "roll_dice", return_value=6):
            client.post(f"/api/steps69/{code}/roll", headers=holder)
    raise AssertionError("could not reach cell 69")
