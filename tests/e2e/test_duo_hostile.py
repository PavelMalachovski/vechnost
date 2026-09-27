"""Whatever a stranger sends, the answer is a 4xx, never a 500.

A 500 is a traceback in the logs and in Sentry on demand, and anyone can
send one of these without an account: a non-ASCII initData hash, a code with
a NUL byte in it, a number JSON cannot even serialise back. Several of them
only break on PostgreSQL (a NUL byte in a text column, an integer past
int32), so this runs in-process on SQLite in every `pytest` and against the
live PostgreSQL server in CI.
"""

from __future__ import annotations

from typing import Any

import pytest

from .harness import Player, Server

CODE_SHAPES = [
    "AB%00CD",                      # NUL byte in the path
    "%C3%A9%C3%A9%C3%A9%C3%A9",     # non-ASCII
    "A" * 300,                      # far too long
    "%20%20",                       # blank
    "..%2F..%2Fetc",                # a path, sort of
    "ÄÖÜ-ÄÖÜ",
]


def _endpoints(code: str) -> list[tuple[str, str, Any]]:
    return [
        ("GET", f"/api/rooms/{code}", None),
        ("POST", f"/api/rooms/{code}/join", None),
        ("POST", f"/api/rooms/{code}/advance", None),
        ("GET", f"/api/compat/{code}", None),
        ("POST", f"/api/compat/{code}/join", None),
        ("POST", f"/api/compat/{code}/answer", {"index": 0, "value": 3}),
        ("GET", f"/api/compat/{code}/result", None),
        ("DELETE", f"/api/compat/{code}", None),
        ("GET", f"/api/steps69/{code}", None),
        ("POST", f"/api/steps69/{code}/join", {}),
        ("GET", f"/api/steps69/{code}/board", None),
        ("POST", f"/api/steps69/{code}/roll", None),
        ("POST", f"/api/steps69/{code}/finale", {"choice": "sync"}),
        ("DELETE", f"/api/steps69/{code}", None),
    ]


@pytest.mark.parametrize("code", CODE_SHAPES)
def test_a_malformed_code_is_a_404_everywhere(server: Server, code: str) -> None:
    alice = server.player("Alice", paid=True)
    for method, path, body in _endpoints(code):
        status = alice.call(method, path, json_body=body).status_code
        assert status in (404, 409, 422), f"{method} {path} -> {status}"


@pytest.mark.parametrize("authorization", [
    "tma auth_date=1&user=%7B%22id%22%3A1%7D&hash=%C3%A9",      # non-ASCII hash
    "tma " + "a" * 5000,                                          # no structure at all
    "tma user=%7Bbroken&auth_date=x&hash=00",                     # broken JSON, bad date
    "Bearer é",
    "tma",
])
def test_a_forged_authorization_is_a_401_not_a_500(server: Server, authorization: str) -> None:
    anon = Player(server, "Anon")
    for method, path in (
        ("GET", "/api/questions"),
        ("GET", "/api/library"),
        ("POST", "/api/rooms"),
        ("GET", "/api/compat/mine"),
        ("GET", "/api/steps69/mine"),
        ("GET", "/api/card?theme=Acquaintance&idx=10&level=1"),
    ):
        body = {"theme": "Acquaintance", "level": 1, "type": "questions"} if method == "POST" else None
        status = anon.call(
            method, path, json_body=body,
            headers={"Authorization": authorization.encode()},  # raw bytes, as a raw client sends
        ).status_code
        assert status < 500, f"{method} {path} with {authorization[:30]!r} -> {status}"


def test_a_forged_admin_token_is_refused_not_crashed(server: Server) -> None:
    anon = Player(server, "Anon")
    for token in ("Bearer é", "Bearer " + "x" * 5000, "Basic abc"):
        status = anon.call(
            "POST", "/admin/sync-products", headers={"Authorization": token.encode()}
        ).status_code
        assert status in (401, 403, 429, 503), f"{token[:20]!r} -> {status}"


@pytest.mark.parametrize("body", [
    {"theme": "Sex", "level": 99_999_999_999, "type": "questions"},
    {"theme": "Acquaintance", "level": -1, "type": "questions"},
    {"theme": "Acquaintance", "level": "one", "type": "questions"},
    {"theme": "Nope", "level": 1, "type": "questions"},
    {"theme": "Acquaintance", "level": 1, "type": "videos"},
    {},
])
def test_a_malformed_room_is_refused(server: Server, body: dict[str, Any]) -> None:
    alice = server.player("Alice", paid=True)
    status = alice.call("POST", "/api/rooms", json_body=body).status_code
    assert status in (404, 422), f"{body} -> {status}"


def test_numbers_json_cannot_hold_are_a_422(server: Server) -> None:
    """`1e309` parses to infinity, and echoing it back in the 422 used to
    raise inside the error handler itself."""
    alice = server.player("Alice", paid=True)
    code = alice.ok("POST", "/api/compat")["code"]
    for raw in (b'{"index": 1e309, "value": 3}', b'{"index": 0, "value": -1e309}', b'{"index": NaN}'):
        response = server.http.post(
            f"/api/compat/{code}/answer", content=raw,
            headers={**alice.headers, "Content-Type": "application/json"},
        )
        assert response.status_code == 422, (raw, response.status_code, response.text[:200])
