"""Tests for the Library HTTP API."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.payments.web import app

client = TestClient(app)


def test_index_lists_all_five_modules():
    body = client.get("/api/library").json()
    ids = [m["id"] for m in body["modules"]]
    assert ids == [
        "dates",
        "fall_in_love",
        "practices_self",
        "practices_couples",
        "reflection",
    ]


def test_paid_caller_gets_every_item():
    body = client.get("/api/library/practices_couples").json()
    assert len(body["items"]) == 25
    assert body["locked"] is False


def test_spicy_category_is_withheld_without_the_nsfw_flag():
    body = client.get("/api/library/dates").json()
    assert "spicy" not in [c["id"] for c in body["categories"]]
    assert body["total"] == 140


def test_withheld_category_is_advertised_by_title_only():
    body = client.get("/api/library/dates").json()
    withheld = body["nsfw_withheld"]
    assert [c["id"] for c in withheld] == ["spicy"]
    assert withheld[0]["total"] == 10
    assert "items" not in withheld[0]


def test_spicy_category_is_served_with_the_nsfw_flag():
    body = client.get("/api/library/dates?nsfw=1").json()
    assert "spicy" in [c["id"] for c in body["categories"]]
    assert body["total"] == 150
    assert body["nsfw_withheld"] == []


def test_daily_module_returns_one_question():
    body = client.get("/api/library/reflection").json()
    assert body["type"] == "daily"
    assert body["question"].strip()
    assert 1 <= body["day"] <= 365


def test_unknown_module_is_404():
    assert client.get("/api/library/nope").status_code == 404


@pytest.fixture
def paywalled(monkeypatch):
    """Run the API as if payments were on and the caller had not paid."""
    from vechnost_bot.payments import library_api

    monkeypatch.setattr(library_api, "_caller_is_paid", _unpaid)
    yield


async def _unpaid(_authorization):
    return False


def test_unpaid_caller_gets_three_items_per_category(paywalled):
    body = client.get("/api/library/dates").json()
    assert body["locked"] is True
    assert all(len(c["items"]) == 3 for c in body["categories"])
    assert body["free_count"] == 21   # 7 non-spicy categories x 3
    assert body["total"] == 140


def test_unpaid_caller_gets_three_practices(paywalled):
    body = client.get("/api/library/practices_couples").json()
    assert len(body["items"]) == 3
    assert body["total"] == 25


def test_free_modules_are_identical_for_unpaid_callers(paywalled):
    body = client.get("/api/library/practices_self").json()
    assert len(body["items"]) == 25
    assert body["locked"] is False


def test_unpaid_caller_with_nsfw_flag_gets_spicy_trimmed_to_three(paywalled):
    body = client.get("/api/library/dates?nsfw=1").json()
    categories = {c["id"]: c for c in body["categories"]}
    assert "spicy" in categories
    assert len(categories["spicy"]["items"]) == 3
    assert categories["spicy"]["total"] == 10
    assert all(len(c["items"]) == 3 for c in body["categories"])
    assert body["total"] == 150


def test_index_count_for_dates_respects_nsfw_flag():
    without = client.get("/api/library").json()
    with_nsfw = client.get("/api/library?nsfw=1").json()
    dates_without = next(m for m in without["modules"] if m["id"] == "dates")
    dates_with = next(m for m in with_nsfw["modules"] if m["id"] == "dates")
    assert dates_without["count"] == 140
    assert dates_with["count"] == 150
