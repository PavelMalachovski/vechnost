"""Tests for the /api/questions payment gate."""

import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

from vechnost_bot.config import settings
from vechnost_bot.payments.web import app
from tests.test_webapp_auth import BOT_TOKEN, make_init_data

client = TestClient(app)


def test_open_when_payments_disabled():
    with patch.object(settings, "enable_payment", False):
        response = client.get("/api/questions?lang=ru")
    assert response.status_code == 200
    assert "themes" in response.json()
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_401_without_authorization_header():
    with patch.object(settings, "enable_payment", True):
        response = client.get("/api/questions?lang=ru")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_401_with_forged_init_data():
    forged = make_init_data(bot_token="1234567890:ANOTHER_TOKEN")
    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "telegram_bot_token", BOT_TOKEN),
    ):
        response = client.get(
            "/api/questions?lang=ru",
            headers={"Authorization": f"tma {forged}"},
        )
    assert response.status_code == 401


def test_403_with_payment_url_when_no_access():
    init_data = make_init_data()
    with (
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "telegram_bot_token", BOT_TOKEN),
        patch(
            "vechnost_bot.payments.web.user_has_access",
            AsyncMock(return_value=False),
        ),
        patch(
            "vechnost_bot.payments.web.get_products_for_purchase",
            AsyncMock(return_value=[]),
        ),
    ):
        response = client.get(
            "/api/questions?lang=ru",
            headers={"Authorization": f"tma {init_data}"},
        )
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "payment_required"
    assert body["payment_url"] == settings.tribute_payment_url


def test_200_with_valid_init_data_and_access():
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
    assert response.json()["lang"] == "en"
    has_access.assert_awaited_once_with(42)
