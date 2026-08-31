"""Tests for the /api/questions freemium gate."""

import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

from tests.test_webapp_auth import BOT_TOKEN, make_init_data
from vechnost_bot.config import settings
from vechnost_bot.freemium import FREE_CARDS_PER_DECK
from vechnost_bot.payments.web import app

client = TestClient(app)


def all_decks(themes: dict):
    """Yield (deck_dict, key) for every questions/tasks list in the payload."""
    for theme in themes.values():
        decks = theme["levels"].values() if "levels" in theme else [theme]
        for deck in decks:
            for key in ("questions", "tasks"):
                if key in deck:
                    yield deck, key


def test_full_content_when_payments_disabled():
    with patch.object(settings, "enable_payment", False):
        response = client.get("/api/questions?lang=ru")
    assert response.status_code == 200
    body = response.json()
    assert body["access"] == {"paid": True}
    for deck, key in all_decks(body["themes"]):
        assert len(deck[key]) == deck[f"{key}_total"]
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_free_slice_without_authorization_header():
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.web.get_products_for_purchase",
            AsyncMock(return_value=[]),
        ),
        patch(
            "vechnost_bot.payments.web.get_price_label",
            AsyncMock(return_value="4,99 €"),
        ),
    ):
        response = client.get("/api/questions?lang=ru")
    assert response.status_code == 200
    body = response.json()
    access = body["access"]
    assert access["paid"] is False
    assert access["free_per_deck"] == FREE_CARDS_PER_DECK
    assert access["payment_url"] == settings.tribute_payment_url
    assert access["price"] == "4,99 €"
    for deck, key in all_decks(body["themes"]):
        assert len(deck[key]) <= FREE_CARDS_PER_DECK
        assert deck[f"{key}_total"] >= len(deck[key])


def test_forged_init_data_gets_free_slice_only():
    forged = make_init_data(bot_token="1234567890:ANOTHER_TOKEN")
    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "telegram_bot_token", BOT_TOKEN),
        patch(
            "vechnost_bot.payments.web.get_products_for_purchase",
            AsyncMock(return_value=[]),
        ),
        patch(
            "vechnost_bot.payments.web.get_price_label",
            AsyncMock(return_value=None),
        ),
    ):
        response = client.get(
            "/api/questions?lang=ru",
            headers={"Authorization": f"tma {forged}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["access"]["paid"] is False
    for deck, key in all_decks(body["themes"]):
        assert len(deck[key]) <= FREE_CARDS_PER_DECK


def test_unpaid_user_gets_free_slice():
    init_data = make_init_data()
    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "telegram_bot_token", BOT_TOKEN),
        patch(
            "vechnost_bot.payments.web.user_has_access",
            AsyncMock(return_value=False),
        ) as has_access,
        patch(
            "vechnost_bot.payments.web.get_products_for_purchase",
            AsyncMock(return_value=[]),
        ),
        patch(
            "vechnost_bot.payments.web.get_price_label",
            AsyncMock(return_value=None),
        ),
    ):
        response = client.get(
            "/api/questions?lang=ru",
            headers={"Authorization": f"tma {init_data}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["access"]["paid"] is False
    assert body["access"]["price"] is None
    has_access.assert_awaited_once_with(42)
    for deck, key in all_decks(body["themes"]):
        assert len(deck[key]) <= FREE_CARDS_PER_DECK


def test_card_image_free_index_is_public():
    with patch.object(settings, "enable_payment", True):
        response = client.get(
            "/api/card?theme=Acquaintance&level=1&idx=0&type=questions&lang=ru"
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 10_000


def test_card_image_paid_index_locked_for_unpaid():
    with patch.object(settings, "enable_payment", True):
        response = client.get(
            "/api/card?theme=Acquaintance&level=1&idx=7&type=questions&lang=ru"
        )
    assert response.status_code == 403


def test_card_image_paid_index_open_with_access():
    init_data = make_init_data()
    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "telegram_bot_token", BOT_TOKEN),
        patch(
            "vechnost_bot.payments.web.user_has_access",
            AsyncMock(return_value=True),
        ),
    ):
        response = client.get(
            "/api/card?theme=Acquaintance&level=1&idx=7&type=questions&lang=ru",
            headers={"Authorization": f"tma {init_data}"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


def test_card_image_unknown_deck_404():
    response = client.get("/api/card?theme=Nope&idx=0")
    assert response.status_code == 404


def test_card_image_out_of_range_404():
    response = client.get(
        "/api/card?theme=Acquaintance&level=1&idx=999&type=questions"
    )
    assert response.status_code == 404


def test_questions_payload_has_bot_url():
    with patch.object(settings, "enable_payment", False):
        response = client.get("/api/questions?lang=ru")
    assert response.json()["bot_url"] == f"https://t.me/{settings.bot_username}"


def test_paid_user_gets_full_content():
    init_data = make_init_data()
    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "telegram_bot_token", BOT_TOKEN),
        patch(
            "vechnost_bot.payments.web.user_has_access",
            AsyncMock(return_value=True),
        ) as has_access,
    ):
        response = client.get(
            "/api/questions?lang=en",
            headers={"Authorization": f"tma {init_data}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["access"] == {"paid": True}
    has_access.assert_awaited_once_with(42)
    totals = [deck[f"{key}_total"] for deck, key in all_decks(body["themes"])]
    assert sum(totals) == 310
    for deck, key in all_decks(body["themes"]):
        assert len(deck[key]) == deck[f"{key}_total"]
