"""Tests for the couple-mode rooms API."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.freemium import FREE_CARDS_PER_DECK
from vechnost_bot.payments.web import app

ALICE = {"X-Guest-Id": "alice-device"}
BOB = {"X-Guest-Id": "bob-device"}
EVE = {"X-Guest-Id": "eve-device"}


@pytest.fixture
def client(tmp_path):
    """TestClient backed by a fresh temp SQLite DB, payments disabled."""
    db_path = tmp_path / "rooms_test.db"
    with (
        patch.object(settings, "database_url", f"sqlite:///{db_path}"),
        patch.object(settings, "enable_payment", False),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield TestClient(app)


def create_room(client, headers=ALICE, theme="Acquaintance", level=1):
    response = client.post(
        "/api/rooms?lang=ru",
        json={"theme": theme, "level": level, "type": "questions"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_room_returns_full_deck_state(client):
    state = create_room(client)
    assert len(state["code"]) == 6
    assert state["total"] == 30  # payments disabled = full deck
    assert state["started"] is False
    assert state["your_role"] == "creator"
    assert state["your_turn"] is False  # no partner yet
    assert state["card_text"]


def test_join_starts_the_game(client):
    code = create_room(client)["code"]
    state = client.post(f"/api/rooms/{code}/join?lang=ru", headers=BOB).json()
    assert state["started"] is True
    assert state["your_role"] == "guest"
    assert state["your_turn"] is False  # creator moves first
    creator_view = client.get(f"/api/rooms/{code}?lang=ru", headers=ALICE).json()
    assert creator_view["your_turn"] is True


def test_room_is_full_for_third_player(client):
    code = create_room(client)["code"]
    client.post(f"/api/rooms/{code}/join", headers=BOB)
    response = client.post(f"/api/rooms/{code}/join", headers=EVE)
    assert response.status_code == 409


def test_outsider_cannot_read_room(client):
    code = create_room(client)["code"]
    client.post(f"/api/rooms/{code}/join", headers=BOB)
    response = client.get(f"/api/rooms/{code}", headers=EVE)
    assert response.status_code == 403


def test_turns_alternate_and_wrong_turn_is_rejected(client):
    code = create_room(client)["code"]
    client.post(f"/api/rooms/{code}/join", headers=BOB)

    # Guest tries to move out of turn
    response = client.post(f"/api/rooms/{code}/advance", headers=BOB)
    assert response.status_code == 403

    # Creator moves, then it's the guest's turn
    state = client.post(f"/api/rooms/{code}/advance", headers=ALICE).json()
    assert state["idx"] == 1
    assert state["your_turn"] is False
    guest_view = client.get(f"/api/rooms/{code}", headers=BOB).json()
    assert guest_view["your_turn"] is True

    # Creator cannot move twice in a row
    response = client.post(f"/api/rooms/{code}/advance", headers=ALICE)
    assert response.status_code == 403


def test_advance_requires_partner(client):
    code = create_room(client)["code"]
    response = client.post(f"/api/rooms/{code}/advance", headers=ALICE)
    assert response.status_code == 409


def test_deck_finishes_after_last_card(client):
    code = create_room(client)["code"]
    client.post(f"/api/rooms/{code}/join", headers=BOB)
    players = [ALICE, BOB]
    state = None
    for i in range(30):
        state = client.post(f"/api/rooms/{code}/advance", headers=players[i % 2]).json()
    assert state["finished"] is True
    response = client.post(f"/api/rooms/{code}/advance", headers=players[0])
    assert response.status_code == 409


def test_unknown_room_404(client):
    assert client.get("/api/rooms/NOPE42", headers=ALICE).status_code == 404


def test_room_requires_identity(client):
    response = client.post(
        "/api/rooms", json={"theme": "Acquaintance", "level": 1, "type": "questions"}
    )
    assert response.status_code == 401


def test_guest_ids_sharing_a_prefix_are_different_players(client):
    """Guest ids used to be truncated to six bytes, so any two that shared
    their first six characters resolved to the same player."""
    alice = {"X-Guest-Id": "alice-device"}
    alice_phone = {"X-Guest-Id": "alice-phone"}

    code = create_room(client, headers=alice)["code"]
    state = client.post(f"/api/rooms/{code}/join", headers=alice_phone).json()
    assert state["your_role"] == "guest"

    # And a third prefix-sharing id is still an outsider, not a re-join.
    response = client.post(f"/api/rooms/{code}/join", headers={"X-Guest-Id": "alice-tablet"})
    assert response.status_code == 409


def test_unpaid_creator_shares_only_free_preview(client):
    async def no_access(user_id):
        return False

    with (
        patch.object(settings, "enable_payment", True),
        patch("vechnost_bot.payments.rooms.user_has_access", no_access),
        patch(
            "vechnost_bot.payments.rooms.validate_init_data",
            lambda init_data, token: {"user": {"id": 42, "first_name": "Оля"}},
        ),
    ):
        response = client.post(
            "/api/rooms?lang=ru",
            json={"theme": "Acquaintance", "level": 1, "type": "questions"},
            headers={"Authorization": "tma stub"},
        )
    assert response.status_code == 200
    assert response.json()["total"] == FREE_CARDS_PER_DECK


def test_expired_room_410(client):
    code = create_room(client)["code"]

    import asyncio

    async def age_room():
        async with database.get_db() as session:
            from vechnost_bot.payments.repositories import RoomRepository

            room = await RoomRepository.get_by_code(session, code)
            room.updated_at = datetime.utcnow() - timedelta(hours=25)
            await session.flush()

    asyncio.run(age_room())
    assert client.get(f"/api/rooms/{code}", headers=ALICE).status_code == 410
