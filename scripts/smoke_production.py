#!/usr/bin/env python3
"""Read-only smoke test of a deployed VECHNOST web process.

Run after a deploy (and on a schedule) against the public URL:

    python scripts/smoke_production.py https://your-app.up.railway.app
    python scripts/smoke_production.py $URL --expect-commit $GITHUB_SHA --wait 600
    python scripts/smoke_production.py $URL --deep   # and the database and the bot

It only reads. It never authenticates, never creates a room, a test or a
board, and never posts to the Tribute webhook, so it leaves no rows behind
and cannot page anyone. What it proves is what a user notices first:

* the process is up and answering (/health), and — with --expect-commit —
  that it is the commit that was just merged (Railway exposes the deployed
  commit as RAILWAY_GIT_COMMIT_SHA, and /health reports it);
* the Mini App page and its content APIs answer with the shape the app
  expects (four decks, forty compatibility questions, four suits);
* the paid and the two-partner endpoints refuse an anonymous caller (401),
  i.e. authentication is switched on rather than silently open;
* the security headers are there, and the page can be framed by Telegram
  Web (a `frame-ancestors` that names web.telegram.org);
* with --deep, that /health/deep is green too: the database answers and the
  bot wrote its heartbeat in the last few minutes. Off by default, because
  it asks about more than the web process (a server started without the
  bot, as CI starts one, is red there by design).

Exit status 0 when every check passes, 1 otherwise; a table goes to stdout,
and to $GITHUB_STEP_SUMMARY when run inside GitHub Actions.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

TELEGRAM_WEB = "https://web.telegram.org"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    ms: float


def _run(name: str, fn: Callable[[], str]) -> Check:
    started = time.perf_counter()
    try:
        detail = fn()
        ok = True
    except Exception as e:  # a failed check is reported, not raised
        detail = f"{type(e).__name__}: {e}"
        ok = False
    return Check(name, ok, detail, (time.perf_counter() - started) * 1000)


def smoke(client: httpx.Client, expect_commit: str | None, deep: bool = False) -> list[Check]:
    checks: list[Check] = []

    def health() -> str:
        r = client.get("/health")
        r.raise_for_status()
        body = r.json()
        assert body.get("status") == "ok", body
        commit = body.get("commit") or "unknown"
        if expect_commit:
            assert commit.startswith(expect_commit[:7]), f"live commit {commit}, expected {expect_commit}"
        return f"commit {commit[:12]}, payments {body.get('payment_enabled')}"

    def app_page() -> str:
        r = client.get("/app/")
        r.raise_for_status()
        assert "telegram-web-app.js" in r.text, "the Mini App page lost Telegram's script"
        assert r.headers.get("x-content-type-options") == "nosniff", "nosniff header missing"
        csp = r.headers.get("content-security-policy", "")
        assert TELEGRAM_WEB in csp, f"Telegram Web may not frame the app: CSP={csp!r}"
        return f"{len(r.content) // 1024} KB"

    def questions() -> str:
        r = client.get("/api/questions?lang=ru")
        r.raise_for_status()
        body = r.json()
        themes = body.get("themes", {})
        assert len(themes) == 4, f"expected four decks, got {sorted(themes)}"
        assert "access" in body, "no access block for the paywall"
        return f"{len(themes)} decks, paid={body['access'].get('paid')}"

    def compat_questions() -> str:
        r = client.get("/api/compat/questions?lang=ru")
        r.raise_for_status()
        body = r.json()
        assert body.get("total") == 40, body.get("total")
        return "40 questions"

    def pieces() -> str:
        r = client.get("/api/steps69/pieces")
        r.raise_for_status()
        assert len(r.json().get("pieces", [])) == 4
        return "4 suits"

    def refuses_strangers() -> str:
        # GET only: reading an unknown code as nobody must be a 401, not a
        # 404 and certainly not a 200. Nothing is created by asking.
        seen = []
        for path in ("/api/rooms/SMOKESMOKESMOKE1", "/api/compat/SMOKESMOKESMOKE1",
                     "/api/steps69/SMOKESMOKESMOKE1", "/api/compat/mine", "/api/steps69/mine"):
            status = client.get(path).status_code
            seen.append(status)
            assert status == 401, f"{path} answered an anonymous caller with {status}"
        return f"{len(seen)} endpoints -> 401"

    def deep_health() -> str:
        # 503 is an answer here, not a transport failure: read its body.
        r = client.get("/health/deep")
        body = r.json()
        found = body.get("checks", {})
        assert r.status_code == 200 and body.get("status") == "ok", f"{r.status_code} {found}"
        return f"database {found.get('database')}, bot beat {found.get('bot_heartbeat_age_s')}s ago"

    named: list[tuple[str, Callable[[], str]]] = [
        ("health", health),
        ("mini app page", app_page),
        ("decks", questions),
        ("compatibility questions", compat_questions),
        ("69 steps suits", pieces),
        ("anonymous callers refused", refuses_strangers),
    ]
    if deep:
        named.append(("database and bot", deep_health))
    for name, fn in named:
        checks.append(_run(name, fn))
    return checks


def wait_for_commit(client: httpx.Client, commit: str, timeout: float) -> None:
    """Poll /health until the deployed commit is `commit`, or give up."""
    deadline = time.monotonic() + timeout
    last = "no answer"
    while time.monotonic() < deadline:
        try:
            live = (client.get("/health").json().get("commit") or "")
            if live.startswith(commit[:7]):
                return
            last = live or "no commit reported"
        except (httpx.HTTPError, ValueError) as e:
            last = str(e)
        time.sleep(15)
    print(f"gave up waiting for {commit[:12]} after {timeout:.0f}s (live: {last})")


def report(checks: list[Check], url: str) -> str:
    lines = [f"### Production smoke: {url}", "", "| | Check | Detail | ms |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {'✅' if c.ok else '❌'} | {c.name} | {c.detail} | {c.ms:.0f} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="base URL of the web process, e.g. https://x.up.railway.app")
    parser.add_argument("--expect-commit", help="fail unless /health reports this commit")
    parser.add_argument("--wait", type=float, default=0,
                        help="seconds to wait for --expect-commit to go live first")
    parser.add_argument("--deep", action="store_true",
                        help="also require /health/deep: the database answers and the bot is beating")
    args = parser.parse_args()

    with httpx.Client(base_url=args.url.rstrip("/"), timeout=20, follow_redirects=True) as client:
        if args.expect_commit and args.wait:
            wait_for_commit(client, args.expect_commit, args.wait)
        checks = smoke(client, args.expect_commit, deep=args.deep)

    table = report(checks, args.url)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(table + "\n")
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
