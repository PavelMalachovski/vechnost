"""«69 ступеней» over HTTP: two pieces, turns, the paywall, and what each phone is told."""

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


def create(client, headers=ALICE, mode="duo", piece="hearts"):
    response = client.post(
        "/api/steps69", json={"mode": mode, "piece": piece}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def started_game(client):
    """A duo game with both seats taken and both pieces chosen."""
    game = create(client)
    join = client.post(
        f"/api/steps69/{game['code']}/join", json={"piece": "spades"}, headers=BOB
    )
    assert join.status_code == 200, join.text
    return game["code"]


def roll(client, code, headers):
    return client.post(f"/api/steps69/{code}/roll", headers=headers)


def _holder(state):
    return ALICE if state["turn"] == 0 else BOB


def _walk_home(client, code, seat=None):
    """Roll until both pieces are on 69, or just one seat's if asked."""
    for _ in range(80):
        state = client.get(f"/api/steps69/{code}", headers=ALICE).json()
        if state["both_home"]:
            return
        if seat is not None:
            mine = state["you"] if state["your_seat"] == seat else state["partner"]
            if mine["home"]:
                return
        with patch.object(steps69, "roll_dice", return_value=6):
            roll(client, code, _holder(state))
    raise AssertionError("could not walk the pieces home")


# ---------------------------------------------------------------------------
# Starting a game
# ---------------------------------------------------------------------------

def test_both_pieces_start_on_cell_one(client):
    game = create(client)
    assert game["you"]["position"] == 1
    assert game["partner"]["position"] == 1
    assert game["you"]["cell"]["kind"] == "start"
    assert game["finished"] is False
    assert len(game["code"]) == 6


def test_the_creator_wears_the_suit_they_picked(client):
    game = create(client, piece="clubs")
    assert game["you"]["piece"] == "clubs"
    assert game["your_seat"] == 0


def test_the_four_suits_are_offered(client):
    body = client.get("/api/steps69/pieces").json()
    assert body["pieces"] == ["hearts", "spades", "clubs", "diamonds"]


def test_a_suit_nobody_plays_is_refused(client):
    response = client.post(
        "/api/steps69", json={"mode": "duo", "piece": "triangles"}, headers=ALICE
    )
    assert response.status_code == 400


def test_the_partner_is_dealt_a_free_suit_instead_of_a_refusal(client):
    """Two identical pieces are indistinguishable, so the second is swapped.

    It used to be a 409, and both ends defaulted to the same suit, so the
    ordinary invite — neither partner having touched the picker — refused the
    partner at the door. Nobody reads "hearts is taken" as "pick another
    suit"; they read it as "this game will not let me in".
    """
    game = create(client, piece="hearts")
    joined = client.post(
        f"/api/steps69/{game['code']}/join", json={"piece": "hearts"}, headers=BOB
    )
    assert joined.status_code == 200
    body = joined.json()
    assert body["you"]["piece"] != "hearts"
    assert body["partner"]["piece"] == "hearts"


def test_the_partner_joins_without_naming_a_suit(client):
    """What an invite link produces: a join with no body worth speaking of."""
    game = create(client, piece="hearts")
    joined = client.post(f"/api/steps69/{game['code']}/join", json={}, headers=BOB)
    assert joined.status_code == 200
    body = joined.json()
    assert body["started"] is True
    assert body["you"]["piece"] and body["you"]["piece"] != "hearts"


def test_the_state_carries_the_link_to_send_the_partner(client):
    game = create(client)
    assert game["invite_url"] and game["code"] in game["invite_url"]
    assert "s69_" in game["invite_url"]


def test_two_phones_play_a_whole_game_through_the_invite_link(client):
    """The path a partner actually takes, end to end.

    The creator makes a game and sends a link; the partner opens it, which
    posts a join with no suit named, reads the board and rolls. This used to
    stop at the door: both ends defaulted to the same suit and the join came
    back 409.
    """
    from vechnost_bot import invites

    game = create(client, piece="hearts")
    link = game["invite_url"]
    screen, code = invites.parse_invite_param(link.split("=")[-1])
    assert (screen, code) == ("steps69", game["code"])

    joined = client.post(f"/api/steps69/{code}/join", json={}, headers=BOB)
    assert joined.status_code == 200, joined.text
    assert joined.json()["started"] is True

    # The guest can read the map and is on the board, not looking at it.
    assert client.get(f"/api/steps69/{code}/board", headers=BOB).status_code == 200

    # 2 and 4 from cell 1 land on 3 and 5, neither of which is a portal:
    # the point here is the two phones, not the board.
    with patch.object(steps69, "roll_dice", return_value=2):
        first = roll(client, code, ALICE)
    assert first.status_code == 200
    assert first.json()["you"]["position"] == 3

    with patch.object(steps69, "roll_dice", return_value=4):
        second = roll(client, code, BOB)
    assert second.status_code == 200
    body = second.json()
    assert body["you"]["position"] == 5, "the guest walks their own board"
    assert body["partner"]["position"] == 3
    assert body["your_turn"] is False, "the turn went back to the creator"


def test_the_partner_takes_their_own_suit(client):
    game = create(client, piece="hearts")
    joined = client.post(
        f"/api/steps69/{game['code']}/join", json={"piece": "diamonds"}, headers=BOB
    ).json()
    assert joined["you"]["piece"] == "diamonds"
    assert joined["partner"]["piece"] == "hearts"
    assert set(joined["pieces_taken"]) == {"hearts", "diamonds"}


def test_a_solo_game_gives_the_second_seat_a_suit_of_its_own(client):
    """One phone still has two players on the board, so it needs two pieces."""
    game = create(client, mode="solo", piece="spades")
    assert game["started"] is True
    assert game["you"]["piece"] == "spades"
    assert game["partner"]["piece"] and game["partner"]["piece"] != "spades"


def test_a_third_player_cannot_take_a_seat(client):
    code = started_game(client)
    response = client.post(
        f"/api/steps69/{code}/join", json={"piece": "clubs"}, headers=EVE
    )
    assert response.status_code == 409


def test_a_solo_game_takes_no_guest(client):
    game = create(client, mode="solo")
    response = client.post(
        f"/api/steps69/{game['code']}/join", json={"piece": "clubs"}, headers=BOB
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Turns and two pieces
# ---------------------------------------------------------------------------

def test_nobody_rolls_before_the_partner_arrives(client):
    game = create(client)
    assert roll(client, game["code"], ALICE).status_code == 409


def test_the_dice_are_blocked_for_whoever_is_not_on_turn(client):
    code = started_game(client)
    assert roll(client, code, BOB).status_code == 403
    assert roll(client, code, ALICE).status_code == 200
    assert roll(client, code, ALICE).status_code == 403


def test_a_roll_moves_only_the_piece_of_whoever_rolled(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=2):
        rolled = roll(client, code, ALICE).json()
    assert rolled["you"]["position"] == 3
    assert rolled["partner"]["position"] == 1, "the partner's piece must not move"

    partner_view = client.get(f"/api/steps69/{code}", headers=BOB).json()
    assert partner_view["you"]["position"] == 1
    assert partner_view["partner"]["position"] == 3


def test_each_player_counts_their_own_rolls(client):
    """The Joker's tempo rule asks how fast *this* player crossed the board."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=1):
        roll(client, code, ALICE)
        roll(client, code, BOB)
        state = roll(client, code, ALICE).json()
    assert state["you"]["rolls"] == 2
    assert state["partner"]["rolls"] == 1


def test_a_player_who_reaches_sixty_nine_stops_and_the_other_keeps_rolling(client):
    """The board is walked twice. One piece home is half a game."""
    code = started_game(client)
    _walk_home(client, code, seat=0)

    state = client.get(f"/api/steps69/{code}", headers=ALICE).json()
    assert state["you"]["home"] is True
    assert state["partner"]["home"] is False
    assert state["both_home"] is False
    assert state["turn"] == 1, "the turn must sit with the piece still walking"
    assert roll(client, code, ALICE).status_code in (403, 409)

    assert roll(client, code, BOB).status_code == 200
    after = client.get(f"/api/steps69/{code}", headers=BOB).json()
    assert after["turn"] == 1, "the finished partner is skipped, not given a turn"


def test_a_stranger_can_neither_watch_nor_roll(client):
    code = started_game(client)
    assert client.get(f"/api/steps69/{code}", headers=EVE).status_code == 403
    assert roll(client, code, EVE).status_code == 403
    assert client.get(f"/api/steps69/{code}/board", headers=EVE).status_code == 403


# ---------------------------------------------------------------------------
# Portals
# ---------------------------------------------------------------------------

def test_a_ladder_moves_the_piece_the_moment_it_is_landed_on(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=3):  # 1 -> 4 -> 18
        rolled = roll(client, code, ALICE).json()
    assert rolled["last"]["landed"] == 4
    assert rolled["last"]["seat"] == 0
    assert rolled["you"]["position"] == 18
    assert rolled["last"]["event"] == "ladder"
    assert rolled["last"]["message"]


def test_a_snake_drags_the_piece_back(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        roll(client, code, ALICE)   # alice 1 -> 7
        roll(client, code, BOB)     # bob   1 -> 7
        rolled = roll(client, code, ALICE).json()  # alice 7 -> 13 -> 2
    assert rolled["last"]["landed"] == 13
    assert rolled["you"]["position"] == 2
    assert rolled["last"]["event"] == "snake"
    assert rolled["partner"]["position"] == 7, "only the mover falls"


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def test_the_player_standing_on_a_secret_reads_it_and_the_partner_does_not(client):
    """The brief: «Текст под спойлером должен быть уникальным для каждого игрока»."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=4):  # alice 1 -> 5, a secret
        mover = roll(client, code, ALICE).json()
    watcher = client.get(f"/api/steps69/{code}", headers=BOB).json()

    assert mover["you"]["cell"]["kind"] == "secret"
    assert mover["you"]["cell"]["secret"]
    assert mover["you"]["cell"]["partner"] is None
    # Bob sees Alice standing on it, and gets only the line written for him.
    assert watcher["partner"]["cell"]["secret"] is None
    assert watcher["partner"]["cell"]["partner"]


def test_the_partners_secret_never_reaches_the_wire(client):
    """Asserted on the raw body rather than a parsed field: a leak under an
    unexpected key would slip past a field-level check."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=4):
        roll(client, code, ALICE)

    watcher = client.get(f"/api/steps69/{code}", headers=BOB)
    assert steps69.cell(5).secret not in watcher.text


def test_one_phone_shows_both_halves(client):
    game = create(client, mode="solo")
    with patch.object(steps69, "roll_dice", return_value=4):
        rolled = roll(client, game["code"], ALICE).json()
    assert rolled["you"]["cell"]["secret"] and rolled["you"]["cell"]["partner"]


# ---------------------------------------------------------------------------
# The Joker
# ---------------------------------------------------------------------------

def test_a_joker_deals_one_task_and_both_phones_see_the_same_one(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        roll(client, code, ALICE)   # alice 1 -> 7
        roll(client, code, BOB)
    with patch.object(steps69, "roll_dice", return_value=2):
        mover = roll(client, code, ALICE).json()   # alice 7 -> 9, a joker

    watcher = client.get(f"/api/steps69/{code}", headers=BOB).json()
    assert mover["you"]["cell"]["kind"] == "joker"
    assert mover["you"]["cell"]["joker"]["text"]
    assert watcher["partner"]["cell"]["joker"] == mover["you"]["cell"]["joker"]
    # Polling again must not redraw.
    assert client.get(f"/api/steps69/{code}", headers=ALICE).json()["you"]["cell"]["joker"] \
        == mover["you"]["cell"]["joker"]


def test_each_piece_carries_its_own_joker(client):
    """Two players can stand on two different Jokers at once."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        roll(client, code, ALICE)
        roll(client, code, BOB)
    with patch.object(steps69, "roll_dice", return_value=2):
        roll(client, code, ALICE)   # alice -> 9, joker
        state = roll(client, code, BOB).json()   # bob -> 9, joker

    assert state["you"]["cell"]["kind"] == "joker"
    assert state["partner"]["cell"]["kind"] == "joker"
    # Same game never deals one task twice.
    assert state["you"]["cell"]["joker"]["id"] != state["partner"]["cell"]["joker"]["id"]


def test_the_joker_clears_when_the_piece_moves_on(client):
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=6):
        roll(client, code, ALICE)
        roll(client, code, BOB)
    with patch.object(steps69, "roll_dice", return_value=2):
        joker = roll(client, code, ALICE).json()
    assert joker["you"]["cell"]["joker"]
    with patch.object(steps69, "roll_dice", return_value=1):
        roll(client, code, BOB)
        after = roll(client, code, ALICE).json()
    assert "joker" not in after["you"]["cell"]


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
# The finale
# ---------------------------------------------------------------------------

def test_the_finale_waits_for_both_pieces(client):
    code = started_game(client)
    _walk_home(client, code, seat=0)
    response = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE
    )
    assert response.status_code == 409


def test_the_finale_opens_when_both_are_home(client):
    code = started_game(client)
    _walk_home(client, code)
    state = client.get(f"/api/steps69/{code}", headers=ALICE).json()
    assert state["both_home"] is True
    assert {c["id"] for c in state["finale"]["choices"]} == {"sync", "taking_turns"}
    assert state["your_turn"] is False


def test_the_dice_are_dead_once_a_piece_is_home(client):
    code = started_game(client)
    _walk_home(client, code)
    for headers in (ALICE, BOB):
        assert roll(client, code, headers).status_code in (403, 409)


def test_choosing_a_finale_ends_the_game(client):
    code = started_game(client)
    _walk_home(client, code)
    done = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE
    ).json()
    assert done["finished"] is True
    assert done["finale_choice"] == "sync"


def test_the_first_choice_stands_when_both_partners_tap(client):
    code = started_game(client)
    _walk_home(client, code)
    client.post(f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE)
    second = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "taking_turns"}, headers=BOB
    )
    assert second.status_code == 409
    assert client.get(f"/api/steps69/{code}", headers=BOB).json()["finale_choice"] == "sync"


def test_an_unknown_finale_is_refused(client):
    code = started_game(client)
    _walk_home(client, code)
    response = client.post(
        f"/api/steps69/{code}/finale", json={"choice": "whatever"}, headers=ALICE
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Coming back later, and starting over
# ---------------------------------------------------------------------------

def test_a_game_in_play_can_be_found_again(client):
    """Leaving the screen is not leaving the game: the pieces stay put."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=2):
        roll(client, code, ALICE)

    mine = client.get("/api/steps69/mine", headers=BOB)
    assert mine.status_code == 200
    assert mine.json()["code"] == code
    assert mine.json()["partner"]["position"] == 3


def test_a_finished_game_is_not_offered_to_continue(client):
    code = started_game(client)
    _walk_home(client, code)
    client.post(f"/api/steps69/{code}/finale", json={"choice": "sync"}, headers=ALICE)
    assert client.get("/api/steps69/mine", headers=ALICE).status_code == 404


def test_starting_over_leaves_no_game_behind(client):
    """"Начать заново" deletes first: otherwise /mine keeps offering to resume
    the board the pair just walked away from."""
    code = started_game(client)
    with patch.object(steps69, "roll_dice", return_value=2):
        roll(client, code, ALICE)
    assert client.delete(f"/api/steps69/{code}", headers=ALICE).status_code == 200
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
        patch("vechnost_bot.payments.steps69_api.user_has_access", return_value=False),
    ):
        response = client.post(
            "/api/steps69", json={"mode": "duo", "piece": "hearts"},
            headers={"Authorization": "tma x"},
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
            "/api/steps69", json={"mode": "duo", "piece": "hearts"},
            headers={"Authorization": "tma x"},
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
        patch("vechnost_bot.payments.steps69_api.user_has_access", side_effect=[True]),
    ):
        created = client.post(
            "/api/steps69", json={"mode": "duo", "piece": "hearts"},
            headers={"Authorization": "tma payer"},
        )
        assert created.status_code == 200
        code = created.json()["code"]

        joined = client.post(
            f"/api/steps69/{code}/join", json={"piece": "spades"},
            headers={"Authorization": "tma guest"},
        )
        assert joined.status_code == 200

        board = client.get(
            f"/api/steps69/{code}/board", headers={"Authorization": "tma guest"}
        )
        assert board.status_code == 200


def test_an_anonymous_caller_is_refused_when_payments_are_on(client):
    with patch.object(settings, "enable_payment", True):
        body = {"mode": "duo", "piece": "hearts"}
        assert client.post("/api/steps69", json=body).status_code == 401
        assert client.post("/api/steps69", json=body, headers=ALICE).status_code == 401
