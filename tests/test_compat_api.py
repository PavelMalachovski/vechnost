"""Tests for the compatibility test's HTTP API."""

import os

from fastapi.testclient import TestClient

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.payments.web import app

client = TestClient(app)
HEAD_A = {"X-Guest-Id": "partner-a"}
HEAD_B = {"X-Guest-Id": "partner-b"}
HEAD_C = {"X-Guest-Id": "stranger"}


def _create(headers=HEAD_A):
    return client.post("/api/compat", headers=headers).json()


def _answer_all(code, headers, value):
    for index in range(40):
        res = client.post(
            f"/api/compat/{code}/answer",
            headers=headers,
            json={"index": index, "value": value},
        )
        assert res.status_code == 200, res.text


def test_create_returns_a_six_character_code():
    body = _create()
    assert len(body["code"]) == 6
    assert body["answered"] == 0
    assert body["partner_answered"] == 0
    assert body["finished"] is False


def test_join_then_both_answer_then_result():
    code = _create()["code"]
    joined = client.post(f"/api/compat/{code}/join", headers=HEAD_B).json()
    assert joined["started"] is True

    _answer_all(code, HEAD_A, 5)
    state = client.get(f"/api/compat/{code}", headers=HEAD_B).json()
    assert state["partner_answered"] == 40
    assert state["answered"] == 0
    assert state["finished"] is False

    assert client.get(f"/api/compat/{code}/result", headers=HEAD_A).status_code == 409

    _answer_all(code, HEAD_B, 5)
    result = client.get(f"/api/compat/{code}/result", headers=HEAD_A).json()
    assert result["percent"] == 100
    assert len(result["spheres"]) == 8


def test_state_never_carries_the_partners_answers():
    """The feature's privacy promise, asserted on raw response text."""
    code = _create()["code"]
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


def test_result_never_carries_raw_answers():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(code, HEAD_A, 4)
    _answer_all(code, HEAD_B, 2)
    body = client.get(f"/api/compat/{code}/result", headers=HEAD_A).text
    assert "creator_answers" not in body
    assert "guest_answers" not in body


def test_a_third_party_is_refused():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    assert client.get(f"/api/compat/{code}", headers=HEAD_C).status_code == 403


def test_unknown_code_is_404():
    assert client.get("/api/compat/ZZZZZZ", headers=HEAD_A).status_code == 404


def test_answer_validates_its_input():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for payload in ({"index": 40, "value": 3}, {"index": 0, "value": 6},
                    {"index": -1, "value": 3}, {"index": 0, "value": 0}):
        res = client.post(f"/api/compat/{code}/answer", headers=HEAD_A, json=payload)
        assert res.status_code == 422, payload


def test_answering_before_a_partner_joins_is_refused():
    code = _create()["code"]
    res = client.post(
        f"/api/compat/{code}/answer", headers=HEAD_A, json={"index": 0, "value": 3}
    )
    assert res.status_code == 409


def test_a_second_guest_cannot_join():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    assert client.post(f"/api/compat/{code}/join", headers=HEAD_C).status_code == 409


def test_mine_returns_the_latest_completed_session():
    assert client.get("/api/compat/mine", headers=HEAD_C).status_code == 404

    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(code, HEAD_A, 5)
    _answer_all(code, HEAD_B, 5)

    mine = client.get("/api/compat/mine", headers=HEAD_A).json()
    assert mine["code"] == code
    assert mine["result"]["percent"] == 100
