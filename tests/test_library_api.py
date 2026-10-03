"""Tests for the Library HTTP API."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.config import settings
from vechnost_bot.i18n import Language
from vechnost_bot.library import load_guide
from vechnost_bot.payments.web import app

client = TestClient(app)


def test_index_lists_every_module_in_order():
    body = client.get("/api/library").json()
    ids = [m["id"] for m in body["modules"]]
    assert ids == [
        "dates",
        "fall_in_love",
        "practices_self",
        "practices_couples",
        "nude_guide",
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
    assert body["free_count"] == 21  # 7 non-spicy categories x 3
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


# ---------------------------------------------------------------------------
# The guide: a module served as a document rather than a deck
# ---------------------------------------------------------------------------


def test_a_guide_arrives_as_ordered_steps():
    body = client.get("/api/library/nude_guide").json()
    assert body["type"] == "guide"
    assert [s["number"] for s in body["steps"]] == [1, 2, 5]
    assert body["intro"].strip()
    assert all(i["art"] for s in body["steps"] for i in s["items"])


def test_a_guides_pose_steps_wait_for_the_age_confirmation():
    """Advertised by title and size only, never by content — the same rule
    the Library's categories follow, and the only way the gate is reachable."""
    body = client.get("/api/library/nude_guide").json()
    withheld = {w["id"]: w["total"] for w in body["nsfw_withheld"]}
    assert withheld == {"her": 9, "him": 10}
    assert "her" not in [s["id"] for s in body["steps"]]

    confirmed = client.get("/api/library/nude_guide?nsfw=1").json()
    assert [s["id"] for s in confirmed["steps"]] == ["light", "camera", "her", "him", "edit"]


def test_the_craft_steps_are_in_front_of_the_age_gate():
    """Light, camera and what to do with the pictures afterwards are not
    nudity, and the safety advice least of all."""
    body = client.get("/api/library/nude_guide").json()
    assert [s["id"] for s in body["steps"]] == ["light", "camera", "edit"]


def test_an_unpaid_caller_gets_the_first_step_and_no_more():
    """The guide is paid; the step about light is a real teaser on its own."""
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.library_api.validate_init_data",
            return_value={"user": {"id": 4242, "first_name": "Unpaid"}},
        ),
        patch("vechnost_bot.payments.library_api.user_has_access", return_value=False),
    ):
        body = client.get(
            "/api/library/nude_guide?nsfw=1", headers={"Authorization": "tma x"}
        ).json()

    assert body["locked"] is True
    assert [s["id"] for s in body["steps"]] == ["light"]
    assert body["free_count"] == 4
    assert body["total"] == 28


def test_an_unpaid_caller_never_receives_the_pose_text():
    """Asserted on the raw body: a leak under an unexpected key would slip
    past a field-level check."""
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.library_api.validate_init_data",
            return_value={"user": {"id": 4243, "first_name": "Unpaid"}},
        ),
        patch("vechnost_bot.payments.library_api.user_has_access", return_value=False),
    ):
        response = client.get("/api/library/nude_guide?nsfw=1", headers={"Authorization": "tma x"})

    poses = [
        i.text
        for s in load_guide("nude_guide", Language.RUSSIAN)
        if s.id in ("her", "him")
        for i in s.items
    ]
    for text in poses:
        assert text not in response.text


# --- the masterclass's pictures ------------------------------------------


def _unpaid_caller():
    return (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.library_api.validate_init_data",
            return_value={"user": {"id": 4244, "first_name": "Unpaid"}},
        ),
        patch("vechnost_bot.payments.library_api.user_has_access", return_value=False),
    )


def test_a_guide_picture_is_served_as_webp():
    res = client.get("/api/library/nude_guide/art/light-side")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/webp"
    assert res.content[:4] == b"RIFF" and res.content[8:12] == b"WEBP"
    # Whether it is served depends on who asks: no shared cache may keep it.
    assert "private" in res.headers["cache-control"]
    assert "content-encoding" not in res.headers


def test_a_pose_picture_waits_for_the_age_confirmation():
    assert client.get("/api/library/nude_guide/art/her-1").status_code == 404
    assert client.get("/api/library/nude_guide/art/her-1?nsfw=1").status_code == 200


def test_an_unpaid_caller_gets_the_free_steps_pictures_and_no_more():
    """The pictures of a paid step are paid like its words, and a refused
    one is the same 404 as a key that does not exist - no oracle."""
    headers = {"Authorization": "tma x"}
    first, second, third = _unpaid_caller()
    with first, second, third:
        free = client.get("/api/library/nude_guide/art/light-side", headers=headers)
        assert free.status_code == 200
        missing = client.get("/api/library/nude_guide/art/no-such-picture?nsfw=1", headers=headers)
        for key in ("camera-height", "her-1", "him-10", "edit-privacy"):
            res = client.get(f"/api/library/nude_guide/art/{key}?nsfw=1", headers=headers)
            assert res.status_code == 404, key
            assert res.content == missing.content, key


def test_every_item_the_guide_sends_has_its_picture():
    body = client.get("/api/library/nude_guide?nsfw=1").json()
    for step in body["steps"]:
        for item in step["items"]:
            res = client.get(f"/api/library/nude_guide/art/{item['art']}?nsfw=1")
            assert res.status_code == 200, item["art"]


def test_each_picture_travels_with_its_fingerprint():
    """A browser keeps a picture for a day, and a re-rendered picture keeps
    its key («Вдохновение» took over him-8 from «Взгляд»): the fingerprint
    of the bytes goes in the address the page asks for, so the new picture
    is fetched rather than yesterday's shown."""
    import hashlib

    from vechnost_bot.library import guide_art_path

    body = client.get("/api/library/nude_guide?nsfw=1").json()
    items = [item for step in body["steps"] for item in step["items"]]
    for item in items:
        data = guide_art_path("nude_guide", item["art"]).read_bytes()
        assert item["art_rev"] == hashlib.sha256(data).hexdigest()[:12], item["art"]
        res = client.get(f"/api/library/nude_guide/art/{item['art']}?nsfw=1&v={item['art_rev']}")
        assert res.status_code == 200 and res.content == data, item["art"]
    assert len({item["art_rev"] for item in items}) == len(items)


def test_a_picture_key_is_never_a_path():
    # A dot segment travels encoded: the client resolves a bare `..` before
    # sending, and the request lands on the module's own route instead.
    keys = ("%2E%2E", "%2E%2E%2Flight-side", "...", "LIGHT-SIDE", "light_side", "light-side.webp")
    for key in (*keys, "-light", "light-"):
        assert client.get(f"/api/library/nude_guide/art/{key}?nsfw=1").status_code == 404, key


def test_only_a_guide_has_pictures():
    assert client.get("/api/library/dates/art/light-side").status_code == 404
    assert client.get("/api/library/nope/art/light-side").status_code == 404
