"""Tests for the compatibility test's HTTP API."""

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.compat_api as compat_api
import vechnost_bot.payments.database as database
from vechnost_bot import invites
from vechnost_bot.config import settings
from vechnost_bot.payments.web import app

HEAD_A = {"X-Guest-Id": "partner-a"}
HEAD_B = {"X-Guest-Id": "partner-b"}
HEAD_C = {"X-Guest-Id": "stranger"}


@pytest.fixture
def notifier():
    """Stand in for the Telegram push.

    Without this a fake token is enough for `_bot()` to build a real `Bot`,
    and every test that completes a session fires two live HTTPS requests at
    api.telegram.org. They fail as InvalidToken and are swallowed, so the
    suite passes either way — until CI has no network and they become
    connect timeouts.
    """
    with patch.object(
        compat_api, "notify_result_ready", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def client(tmp_path, notifier):
    """TestClient backed by a fresh temp SQLite DB, payments disabled."""
    db_path = tmp_path / "compat_test.db"
    with (
        patch.object(settings, "database_url", f"sqlite:///{db_path}"),
        patch.object(settings, "enable_payment", False),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield TestClient(app)


def _create(client, headers=HEAD_A):
    return client.post("/api/compat", headers=headers).json()


def _answer_all(client, code, headers, value):
    for index in range(40):
        res = client.post(
            f"/api/compat/{code}/answer",
            headers=headers,
            json={"index": index, "value": value},
        )
        assert res.status_code == 200, res.text


def test_create_returns_a_six_character_code(client):
    body = _create(client)
    assert len(body["code"]) == invites.CODE_LENGTH
    assert body["answered"] == 0
    assert body["partner_answered"] == 0
    assert body["finished"] is False


def test_join_then_both_answer_then_result(client):
    code = _create(client)["code"]
    joined = client.post(f"/api/compat/{code}/join", headers=HEAD_B).json()
    assert joined["started"] is True

    _answer_all(client, code, HEAD_A, 5)
    state = client.get(f"/api/compat/{code}", headers=HEAD_B).json()
    assert state["partner_answered"] == 40
    assert state["answered"] == 0
    assert state["finished"] is False

    assert client.get(f"/api/compat/{code}/result", headers=HEAD_A).status_code == 409

    _answer_all(client, code, HEAD_B, 5)
    result = client.get(f"/api/compat/{code}/result", headers=HEAD_A).json()
    assert result["percent"] == 100
    assert len(result["spheres"]) == 8


def test_state_never_carries_the_partners_answers(client):
    """The feature's privacy promise, asserted on raw response text."""
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for index in range(40):
        client.post(
            f"/api/compat/{code}/answer",
            headers=HEAD_A,
            json={"index": index, "value": (index % 5) + 1},
        )
    body = client.get(f"/api/compat/{code}", headers=HEAD_B).text
    assert "creator_answers" not in body
    assert "guest_answers" not in body
    assert "answers" not in body


def test_result_never_carries_raw_answers(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(client, code, HEAD_A, 4)
    _answer_all(client, code, HEAD_B, 2)
    body = client.get(f"/api/compat/{code}/result", headers=HEAD_A).text
    assert "creator_answers" not in body
    assert "guest_answers" not in body


def test_result_carries_no_sphere_score(client):
    """A sphere score is invertible, so it must not reach either client.

    `score` is `(avg_a + avg_b) / 2` over five questions. A partner knows
    their own five, so `sum_theirs = 10 * score - sum_mine` — exact, every
    time. It stays inside `build_result` as a parallel list.
    """
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(client, code, HEAD_A, 4)
    _answer_all(client, code, HEAD_B, 2)

    assert "score" not in client.get(
        f"/api/compat/{code}/result", headers=HEAD_A
    ).text
    assert "score" not in client.get("/api/compat/mine", headers=HEAD_A).text


def test_a_partner_cannot_reconstruct_the_others_sphere_sums(client):
    """Knowing your own answers plus the whole payload must not yield theirs.

    Fails before the fix: `score` was in every sphere object, and the loop
    below would have found `10 * score - sum_mine` for all eight spheres.
    """
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)

    # Partner A's answers are known to A; B's are the secret.
    mine = [(i % 5) + 1 for i in range(40)]
    theirs = [((i * 3) % 5) + 1 for i in range(40)]
    for index, value in enumerate(mine):
        client.post(f"/api/compat/{code}/answer", headers=HEAD_A,
                    json={"index": index, "value": value})
    for index, value in enumerate(theirs):
        client.post(f"/api/compat/{code}/answer", headers=HEAD_B,
                    json={"index": index, "value": value})

    payload = client.get(f"/api/compat/{code}/result", headers=HEAD_A).json()
    secret_sums = [sum(theirs[s * 5:s * 5 + 5]) for s in range(8)]

    # Every number anywhere in the payload, however nested.
    def numbers(node):
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            yield float(node)
        elif isinstance(node, dict):
            for value in node.values():
                yield from numbers(value)
        elif isinstance(node, list):
            for value in node:
                yield from numbers(value)

    found = set(numbers(payload))
    for sphere_index, secret in enumerate(secret_sums):
        mine_sum = sum(mine[sphere_index * 5:sphere_index * 5 + 5])
        # No number the payload carries inverts to the partner's sphere sum.
        assert not any(
            abs(10 * n - mine_sum - secret) < 1e-9 for n in found
        ), f"sphere {sphere_index}: partner's sum recoverable from the payload"


def test_a_third_party_is_refused(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    assert client.get(f"/api/compat/{code}", headers=HEAD_C).status_code == 403


def test_unknown_code_is_404(client):
    assert client.get("/api/compat/ZZZZZZ", headers=HEAD_A).status_code == 404


def test_answer_validates_its_input(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for payload in ({"index": 40, "value": 3}, {"index": 0, "value": 6},
                    {"index": -1, "value": 3}, {"index": 0, "value": 0}):
        res = client.post(f"/api/compat/{code}/answer", headers=HEAD_A, json=payload)
        assert res.status_code == 422, payload


def test_answering_before_a_partner_joins_is_refused(client):
    code = _create(client)["code"]
    res = client.post(
        f"/api/compat/{code}/answer", headers=HEAD_A, json={"index": 0, "value": 3}
    )
    assert res.status_code == 409


def test_a_second_guest_cannot_join(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    assert client.post(f"/api/compat/{code}/join", headers=HEAD_C).status_code == 409


def test_mine_returns_the_latest_completed_session(client):
    assert client.get("/api/compat/mine", headers=HEAD_C).status_code == 404

    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(client, code, HEAD_A, 5)
    _answer_all(client, code, HEAD_B, 5)

    mine = client.get("/api/compat/mine", headers=HEAD_A).json()
    assert mine["code"] == code
    assert mine["result"]["percent"] == 100


def test_answering_after_completion_is_refused_and_result_is_unchanged(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(client, code, HEAD_A, 5)
    _answer_all(client, code, HEAD_B, 5)

    before = client.get(f"/api/compat/{code}/result", headers=HEAD_A).json()

    res = client.post(
        f"/api/compat/{code}/answer", headers=HEAD_A, json={"index": 0, "value": 1}
    )
    assert res.status_code == 409

    after = client.get(f"/api/compat/{code}/result", headers=HEAD_A).json()
    assert after == before


def test_the_fortieth_answer_notifies_both_partners_once(client, notifier):
    """The push is the only thing that brings the first partner back."""
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)

    _answer_all(client, code, HEAD_A, 5)
    assert notifier.await_count == 0, "nobody is told before both are done"

    _answer_all(client, code, HEAD_B, 5)
    assert notifier.await_count == 1

    recipients, kwargs = notifier.await_args
    state = client.get(f"/api/compat/{code}", headers=HEAD_A).json()
    assert kwargs["code"] == code
    assert len(recipients[0]) == 2
    assert all(isinstance(user_id, int) for user_id in recipients[0])
    assert state["finished"] is True


def test_state_returns_only_the_callers_own_answered_indices(client):
    """The resume signal must not become a channel for the partner's answers."""
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for index in (0, 1, 7):
        client.post(f"/api/compat/{code}/answer", headers=HEAD_A,
                    json={"index": index, "value": 3})

    assert client.get(f"/api/compat/{code}", headers=HEAD_A).json()[
        "answered_indices"] == [0, 1, 7]
    # The partner sees their own empty list, not A's three.
    assert client.get(f"/api/compat/{code}", headers=HEAD_B).json()[
        "answered_indices"] == []


def test_either_participant_can_delete_the_test(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(client, code, HEAD_A, 5)
    _answer_all(client, code, HEAD_B, 5)

    # The guest, not the creator: consent to keep the answers is unanimous.
    assert client.delete(f"/api/compat/{code}", headers=HEAD_B).status_code == 200
    assert client.get(f"/api/compat/{code}", headers=HEAD_A).status_code == 404
    assert client.get("/api/compat/mine", headers=HEAD_A).status_code == 404


def test_a_third_party_cannot_delete_the_test(client):
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)

    assert client.delete(f"/api/compat/{code}", headers=HEAD_C).status_code == 403
    assert client.get(f"/api/compat/{code}", headers=HEAD_A).status_code == 200


def test_deleting_an_unknown_code_is_404(client):
    assert client.delete("/api/compat/ZZZZZZ", headers=HEAD_A).status_code == 404


def test_an_unfinished_test_can_be_deleted_too(client):
    """The couple who stop halfway are the ones with answers they can't remove."""
    code = _create(client)["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for index in range(20):
        client.post(f"/api/compat/{code}/answer", headers=HEAD_A,
                    json={"index": index, "value": 4})

    assert client.delete(f"/api/compat/{code}", headers=HEAD_A).status_code == 200
    assert client.get(f"/api/compat/{code}", headers=HEAD_A).status_code == 404
