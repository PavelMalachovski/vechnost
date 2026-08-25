"""The four holes the audit turned up, each with a test that fails without the fix.

S1 an unsigned webhook granted lifetime access, S2 nothing was rate limited,
S3 the admin token was compared byte by byte, S4 exception text went to the
caller.
"""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments import throttle
from vechnost_bot.payments.signature import verify_tribute_signature
from vechnost_bot.payments.web import app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "hardening.db"
    with (
        patch.object(settings, "database_url", f"sqlite:///{db_path}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield TestClient(app)


# --------------------------------------------------------------------------
# S1: a webhook with no secret configured
# --------------------------------------------------------------------------

def test_an_unsigned_webhook_is_refused_when_payments_are_on():
    """The whole paywall rests on this. A Tribute webhook grants lifetime
    access, so accepting one nobody signed means anyone who can reach the
    endpoint is a paying customer."""
    with (
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "enable_payment", True),
    ):
        assert verify_tribute_signature({}, b'{"name":"new_digital_product"}') is False


def test_an_unsigned_webhook_still_passes_with_payments_off():
    """Local development has no secret and no paywall to bypass."""
    with (
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "enable_payment", False),
    ):
        assert verify_tribute_signature({}, b"{}") is True


def test_a_forged_signature_is_refused():
    with patch.object(settings, "webhook_secret", "s3cret"):
        assert verify_tribute_signature(
            {"X-Tribute-Signature": "0" * 64}, b'{"name":"x"}'
        ) is False


def test_a_real_signature_is_accepted():
    import hashlib
    import hmac

    body = b'{"name":"new_digital_product"}'
    signature = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    with patch.object(settings, "webhook_secret", "s3cret"):
        assert verify_tribute_signature(
            {"X-Tribute-Signature": signature}, body
        ) is True


def test_the_endpoint_rejects_the_forged_grant_end_to_end(client):
    """The attack itself: POST your own telegram_user_id, become a customer."""
    with (
        patch.object(settings, "webhook_secret", None),
        patch.object(settings, "enable_payment", True),
    ):
        response = client.post(
            "/webhooks/tribute",
            json={
                "name": "new_digital_product",
                "payload": {"telegram_user_id": 424242, "amount": 0},
            },
        )
    assert response.status_code == 401


# --------------------------------------------------------------------------
# S2: rate limiting
# --------------------------------------------------------------------------

def test_the_join_budget_runs_out():
    throttle.reset()
    limit, _ = throttle.LIMITS["join"]
    for _ in range(limit):
        throttle.check("join", "10.0.0.1")
    with pytest.raises(Exception) as excinfo:
        throttle.check("join", "10.0.0.1")
    assert excinfo.value.status_code == 429


def test_one_clients_budget_is_not_anothers():
    throttle.reset()
    limit, _ = throttle.LIMITS["join"]
    for _ in range(limit):
        throttle.check("join", "10.0.0.1")
    throttle.check("join", "10.0.0.2")  # must not raise


def test_a_client_rotating_its_forwarded_address_still_hits_the_global_ceiling():
    """Per-client budgets alone are theatre: X-Forwarded-For is whatever the
    caller says it is, so one attacker with a fresh value per request would
    never spend a budget. The global ceiling is what actually bounds a sweep
    of the code space."""
    throttle.reset()
    ceiling, _ = throttle.GLOBAL_LIMITS["join"]
    for n in range(ceiling):
        throttle.check("join", f"10.0.{n // 256}.{n % 256}")
    with pytest.raises(Exception) as excinfo:
        throttle.check("join", "192.168.1.1")
    assert excinfo.value.status_code == 429


def test_guessing_room_codes_is_throttled(client):
    throttle.reset()
    limit, _ = throttle.LIMITS["join"]
    codes = [f"AAAA{n:02d}" for n in range(limit + 2)]
    statuses = [
        client.post(f"/api/rooms/{code}/join", headers={"X-Guest-Id": "eve"}).status_code
        for code in codes
    ]
    assert 429 in statuses, statuses
    # The budget is spent on wrong guesses, not only on hits.
    assert statuses[:limit].count(429) == 0


def test_rendering_cards_is_throttled(client):
    throttle.reset()
    limit, _ = throttle.LIMITS["render"]
    statuses = [
        client.get("/api/card?theme=Acquaintance&level=1&idx=0").status_code
        for _ in range(limit + 2)
    ]
    assert statuses[-1] == 429


def test_the_forwarded_address_wins_over_the_socket_peer():
    """Behind a platform proxy every request arrives from the proxy, so
    keying on the peer would put every user of the product in one bucket."""
    from starlette.requests import Request

    def make(headers, peer):
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
        }
        return Request(scope)

    assert throttle.client_key(make({"x-forwarded-for": "1.2.3.4, 10.0.0.1"}, "10.0.0.1")) == "1.2.3.4"
    assert throttle.client_key(make({}, "10.0.0.1")) == "10.0.0.1"


# --------------------------------------------------------------------------
# S3: the admin token
# --------------------------------------------------------------------------

def test_admin_is_closed_when_no_secret_is_configured(client):
    with (
        patch.object(settings, "admin_token", None),
        patch.object(settings, "tribute_api_key", None),
    ):
        response = client.post(
            "/admin/sync-products", headers={"Authorization": "Bearer anything"}
        )
    assert response.status_code == 503


def test_admin_rejects_a_wrong_token(client):
    with patch.object(settings, "admin_token", "right"):
        response = client.post(
            "/admin/sync-products", headers={"Authorization": "Bearer wrong"}
        )
    assert response.status_code == 401


def test_admin_falls_back_to_the_tribute_key_for_existing_deployments(client):
    with (
        patch.object(settings, "admin_token", None),
        patch.object(settings, "tribute_api_key", "legacy-key"),
    ):
        response = client.post(
            "/admin/sync-products", headers={"Authorization": "Bearer wrong"}
        )
    assert response.status_code == 401  # reached the comparison, not the 503


def test_the_admin_token_is_compared_in_constant_time():
    """A plain `!=` returns at the first differing byte, which turns guessing
    the token into guessing one character at a time."""
    import inspect

    from vechnost_bot.payments import web

    source = inspect.getsource(web.verify_admin_token)
    assert "compare_digest" in source
    assert "!= settings" not in source


def test_admin_guesses_are_throttled(client):
    throttle.reset()
    limit, _ = throttle.LIMITS["admin"]
    with patch.object(settings, "admin_token", "right"):
        statuses = [
            client.post(
                "/admin/sync-products", headers={"Authorization": "Bearer wrong"}
            ).status_code
            for _ in range(limit + 2)
        ]
    assert statuses[-1] == 429


# --------------------------------------------------------------------------
# S4: what the caller is told about a failure
# --------------------------------------------------------------------------

def test_a_crash_inside_the_webhook_tells_the_caller_nothing(client):
    """The detail field goes to whoever sent the request; an unhandled
    exception carries SQL, driver and filesystem fragments."""
    secret = "s3cret"
    with (
        patch.object(settings, "webhook_secret", secret),
        patch(
            "vechnost_bot.payments.web.apply_webhook_event",
            side_effect=RuntimeError("connection to 10.1.2.3:5432 failed: FATAL password"),
        ),
    ):
        response = client.post("/webhooks/tribute", json={"name": "x"})

    assert response.status_code == 500
    body = response.text
    assert "10.1.2.3" not in body
    assert "password" not in body.lower()
    assert "FATAL" not in body


def test_a_failed_product_sync_tells_the_caller_nothing(client):
    with (
        patch.object(settings, "admin_token", "right"),
        patch(
            "vechnost_bot.payments.web.sync_products_from_tribute",
            side_effect=RuntimeError("bearer tok_live_abc123 rejected"),
        ),
    ):
        response = client.post(
            "/admin/sync-products", headers={"Authorization": "Bearer right"}
        )

    assert response.status_code == 500
    assert "tok_live_abc123" not in response.text
