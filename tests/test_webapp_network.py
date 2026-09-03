"""The Mini App's network layer, held by reading the file.

Three things a phone on a bad link ran into: a request with no deadline
left the full-screen loader up until the WebView gave up; the three
pollers reacted to nothing but 404, so an expired initData (401) or a 429
from our own throttle was ignored and the server asked every two seconds
forever; and a poll that left before the user's own move and landed after
it repainted the older state over the newer one.
"""

import re
from pathlib import Path

INDEX = Path("webapp/index.html").read_text(encoding="utf-8")


def _body(name: str) -> str:
    """The source of one top-level function, by its declaration."""
    start = INDEX.index(f"function {name}(")
    return INDEX[start:INDEX.index("\n  }\n", start)]


def test_every_request_has_a_deadline():
    assert "AbortController" in INDEX
    assert "REQUEST_TIMEOUT_MS" in INDEX
    for fn in ("coopFetch", "libFetch", "loadData"):
        assert "timedFetch(" in _body(fn), f"{fn} still calls fetch() with no deadline"


def test_errors_carry_their_status_everywhere():
    """statusMessage() can only word a failure it can see the status of."""
    for fn in ("coopFetch", "libFetch", "loadData"):
        assert "httpError(" in _body(fn), fn


def test_the_pollers_share_one_loop_that_backs_off_and_stops():
    assert "setInterval(" not in INDEX, "a bare interval stacks requests and never backs off"
    loop = _body("startPoll")
    assert "e.status === 401" in loop, "an expired initData must stop the loop"
    assert "e.status === 404 || e.status === 410" in loop
    assert "POLL_MAX_MS" in loop, "a 429 or a 5xx must stretch the pause"
    for starter in ("startCoopPoll", "startCompatPoll", "startS69Poll"):
        assert "startPoll(" in _body(starter), starter


def test_an_older_poll_answer_never_repaints_a_newer_move():
    coop = INDEX[INDEX.index("function enterCoopDeck("):INDEX.index("function coopFlyTop(")]
    assert re.search(r"st\.idx < prevIdx\) return", coop), "couple mode may step backwards"
    board = _body("onS69State")
    assert "rolls" in board and "return" in board, "the board may jump back a square"


def test_escape_html_survives_a_missing_field():
    assert "String(s == null ? '' : s)" in _body("escapeHTML")


def test_copying_the_invite_reports_what_actually_happened():
    body = _body("copyInvite")
    assert ".then(" in body, "the clipboard promise is the answer, not the call"
    assert "navigator.clipboard)" in body, "a WebView without a clipboard must not throw"
