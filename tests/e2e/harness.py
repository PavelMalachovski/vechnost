"""Two Telegram users, one server, and every exchange between them on record.

Everything VECHNOST sells to a couple needs two people: a room, the
compatibility test and «69 ступеней» each have a creator and a guest on two
phones, polling one row and writing to it in turns. Unit tests call one
endpoint at a time as one person, so the bugs that live *between* the two
phones — a turn that both or neither may take, a secret that reaches the
wrong screen, a guest who cannot get in — were only ever found by a couple.

This module plays both of them. A `Player` is a real Telegram identity as
far as the server can tell: its requests carry initData signed with the
bot token exactly the way Telegram signs it, so payments stay switched on
and every access check runs. Access is bought the way a customer buys it,
with a Tribute webhook signed by the key Tribute would sign it with.

The same scenarios run against two kinds of server:

* in-process (the default): the FastAPI app behind Starlette's TestClient
  and a throwaway SQLite file, fast enough for every `pytest` run;
* live (`E2E_BASE_URL` set): a real uvicorn over real HTTP, which in CI
  sits on PostgreSQL — the database production runs on and the tests
  otherwise never touch.

Every request is written to a `Transcript`, and a failing test prints it,
so a red run says what each partner did and saw, in order.

Isolation is by identity, not by database: every player is a fresh random
Telegram id and every game a fresh code, so scenarios can share one live
server and one database without seeing each other.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import secrets
import threading
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

# What the server under test must be configured with. The in-process server
# is patched to these; a live server is started with them (see
# `.github/workflows/e2e.yml` and `tests/e2e/README.md`).
E2E_TRIBUTE_KEY = "e2e-tribute-signing-key"
E2E_BOT_USERNAME = "vechnost_e2e_bot"
E2E_WEBAPP_URL = "https://e2e.vechnost.invalid/app/"
# A product id that is not the gift product, so a grant is access of one's own.
E2E_PRODUCT_ID = 424242

_rng = random.SystemRandom()


class HarnessError(AssertionError):
    """A scenario saw something no correct server may do."""


class ServerError(HarnessError):
    """A 5xx. Never acceptable, whatever the players did to provoke it."""


class UnexpectedStatus(HarnessError):
    """A status the scenario did not expect at that step."""


class LeakDetected(HarnessError):
    """A player was shown something that belongs only to their partner."""


def fresh_telegram_id() -> int:
    """A random, realistic Telegram user id no other scenario will draw."""
    return _rng.randint(7_000_000_000, 7_999_999_999)


def fresh_ip() -> str:
    """A client address for the throttle to key on.

    From 198.18.0.0/15 (RFC 2544, benchmarking): wide enough that two
    players in one run practically never share a budget by accident.
    """
    return f"198.{_rng.randint(18, 19)}.{_rng.randint(0, 255)}.{_rng.randint(1, 254)}"


def sign_init_data(
    user: dict[str, Any],
    bot_token: str,
    *,
    auth_date: int | None = None,
    start_param: str | None = None,
) -> str:
    """initData as Telegram signs it for a Mini App.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    — the hash is HMAC-SHA256 over the sorted `key=value` lines, keyed with
    HMAC-SHA256("WebAppData", bot_token). The server checks exactly this,
    so a signature that passes here is one Telegram could have produced.
    """
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAE" + secrets.token_hex(8),
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    if start_param:
        fields["start_param"] = start_param
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def sign_webhook(body: bytes, key: str = E2E_TRIBUTE_KEY) -> str:
    """The `trbt-signature` Tribute sends: hex HMAC-SHA256 of the raw body."""
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def code_from_invite(url: str) -> str:
    """The room/test/game code inside an invite link, whichever shape it has."""
    query = parse_qs(urlsplit(url).query)
    param = (query.get("startapp") or query.get("start") or [""])[0]
    kind, _, code = param.partition("_")
    if not code:
        raise HarnessError(f"invite link carries no code: {url}")
    return code


def walk(value: Any) -> Iterator[tuple[str, Any]]:
    """Every (key, value) pair anywhere inside a JSON document."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield str(key), inner
            yield from walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from walk(inner)


def keys_in(value: Any) -> set[str]:
    """Every field name anywhere in a document.

    Numeric keys are data, not fields — the compat result maps question
    numbers to texts — so they are left out.
    """
    return {key for key, _ in walk(value) if not key.isdigit()}


def assert_absent(body: str, needles: Iterable[str], *, what: str) -> None:
    """Fail if any of `needles` appears anywhere in a raw response body."""
    for needle in needles:
        if needle and needle in body:
            raise LeakDetected(f"{what}: found {needle[:80]!r} in a response")


@dataclass
class Exchange:
    """One request and what came back."""

    who: str
    method: str
    path: str
    status: int
    elapsed_ms: float
    sent: Any = None
    received: Any = None

    def line(self) -> str:
        sent = "" if self.sent is None else " " + _short(self.sent, 80)
        received = _short(self.received, 240)
        return (
            f"{self.who:>8}  {self.method:<6} {self.path}{sent}\n"
            f"{'':>8}  -> {self.status} in {self.elapsed_ms:.0f} ms  {received}"
        )


def _short(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class Transcript:
    """Everything both players did, in order. Printed when a test fails."""

    exchanges: list[Exchange] = field(default_factory=list)

    def add(self, exchange: Exchange) -> None:
        self.exchanges.append(exchange)

    def render(self, last: int = 80) -> str:
        shown = self.exchanges[-last:]
        skipped = len(self.exchanges) - len(shown)
        head = [f"... {skipped} earlier exchange(s) not shown"] if skipped else []
        return "\n".join(head + [exchange.line() for exchange in shown])

    def slowest(self, count: int = 5) -> list[Exchange]:
        return sorted(self.exchanges, key=lambda e: e.elapsed_ms, reverse=True)[:count]


class Player:
    """One Telegram user holding the Mini App open on their own phone."""

    def __init__(
        self,
        server: Server,
        name: str,
        *,
        telegram_id: int | None = None,
        ip: str | None = None,
        auth_date: int | None = None,
    ) -> None:
        self.server = server
        self.name = name
        self.id = telegram_id or fresh_telegram_id()
        self.ip = ip or fresh_ip()
        self.user = {
            "id": self.id,
            "first_name": name,
            "username": f"e2e_{name.lower()}_{self.id % 100000}",
            "language_code": "ru",
            "allows_write_to_pm": True,
        }
        self.init_data = sign_init_data(
            self.user, server.bot_token, auth_date=auth_date
        )

    def __repr__(self) -> str:
        return f"<Player {self.name} {self.id}>"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"tma {self.init_data}",
            # The address the proxy saw: two phones on two networks, or share
            # `ip` to put a couple on one home Wi-Fi. The throttle budgets a
            # signed player by their Telegram id, so the address only keys
            # what carries no valid initData.
            "X-Forwarded-For": self.ip,
        }

    def call(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        expect: int | Iterable[int] | None = None,
        headers: dict[str, str | bytes] | None = None,
    ) -> httpx.Response:
        """One request. A 5xx or an unexpected status fails with the transcript."""
        started = time.perf_counter()
        response = self.server.http.request(
            method,
            path,
            json=json_body,
            headers={**self.headers, **(headers or {})},
        )
        elapsed = (time.perf_counter() - started) * 1000
        try:
            received: Any = response.json()
        except ValueError:
            received = response.text[:500]
        self.server.transcript.add(Exchange(
            who=self.name, method=method, path=path, status=response.status_code,
            elapsed_ms=elapsed, sent=json_body, received=received,
        ))
        if response.status_code >= 500:
            raise ServerError(
                f"{self.name}: {method} {path} -> {response.status_code}: "
                f"{response.text[:500]}"
            )
        if expect is not None:
            allowed = {expect} if isinstance(expect, int) else set(expect)
            if response.status_code not in allowed:
                raise UnexpectedStatus(
                    f"{self.name}: {method} {path} -> {response.status_code}, "
                    f"expected {sorted(allowed)}: {response.text[:500]}"
                )
        return response

    def ok(self, method: str, path: str, json_body: Any = None) -> Any:
        """A request that must succeed; returns the parsed body."""
        return self.call(method, path, json_body=json_body, expect=200).json()

    # The status a request came back with, for scenarios that probe refusals.
    def status(self, method: str, path: str, json_body: Any = None) -> int:
        return self.call(method, path, json_body=json_body).status_code


class Server:
    """The app under test, reached through one HTTP client."""

    def __init__(
        self,
        http: httpx.Client,
        *,
        live: bool,
        bot_token: str,
        telegram: Any = None,
    ) -> None:
        self.http = http
        self.live = live
        self.bot_token = bot_token
        self.telegram = telegram  # a FakeTelegram in-process, None when live
        # The TestClient's event loop, in-process only: the bot is driven on
        # it so the bot and the API share one engine and one database.
        self.portal: Any = None
        self.transcript = Transcript()

    def player(self, name: str, *, paid: bool = False, **kwargs: Any) -> Player:
        player = Player(self, name, **kwargs)
        if paid:
            self.grant(player)
        return player

    # -- payments, the way Tribute delivers them ---------------------------

    def webhook(
        self, name: str, player: Player, *, key: str = E2E_TRIBUTE_KEY, **payload: Any
    ) -> httpx.Response:
        return self.deliver(self.webhook_body(name, player, **payload), key=key, label=f"{name} → {player.name}")

    def webhook_body(self, name: str, player: Player, **payload: Any) -> bytes:
        """One delivery's bytes, in Tribute's shape."""
        now = datetime.now(UTC).isoformat()
        return json.dumps({
            "name": name,
            "created_at": now,
            # A delivery is idempotent on its body hash, so two events for
            # one user must never be byte-identical.
            "sent_at": now,
            "nonce": secrets.token_hex(6),
            "payload": {
                "telegram_user_id": player.id,
                "product_id": E2E_PRODUCT_ID,
                "amount": 49900,
                "currency": "rub",
                **payload,
            },
        }).encode()

    def deliver(
        self, body: bytes, *, key: str = E2E_TRIBUTE_KEY, label: str = "delivery",
        http: httpx.Client | None = None,
    ) -> httpx.Response:
        """POST one delivery, signed. A 503 is Tribute's cue to redeliver,
        so it is returned; any other 5xx fails the scenario."""
        started = time.perf_counter()
        response = (http or self.http).post(
            "/webhooks/tribute",
            content=body,
            headers={
                "Content-Type": "application/json",
                "trbt-signature": sign_webhook(body, key),
                "X-Forwarded-For": fresh_ip(),
            },
        )
        self.transcript.add(Exchange(
            who="tribute", method="POST", path=f"/webhooks/tribute [{label}]",
            status=response.status_code,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            received=response.text[:300],
        ))
        if response.status_code >= 500 and response.status_code != 503:
            raise ServerError(f"{label} -> {response.status_code}: {response.text}")
        return response

    def deliver_all_at_once(self, bodies: list[bytes]) -> list[httpx.Response]:
        """Several deliveries reaching the server at the same instant."""
        barrier = threading.Barrier(len(bodies))
        base_url = str(self.http.base_url)

        def fire(body: bytes) -> httpx.Response:
            with httpx.Client(base_url=base_url, timeout=60) as http:
                barrier.wait()
                return self.deliver(body, label="concurrent delivery", http=http)

        with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
            return list(pool.map(fire, bodies))

    # -- the same instant on several phones ---------------------------------

    def all_at_once(
        self, requests: list[tuple[Player, str, str, Any]]
    ) -> list[httpx.Response]:
        """Fire every (player, method, path, body) at the same moment.

        Each request gets its own connection and waits at a barrier, so they
        reach the server together: that is what two thumbs on two phones do,
        and what one client sending one request after another never does.
        """
        barrier = threading.Barrier(len(requests))
        base_url = str(self.http.base_url)

        def fire(player: Player, method: str, path: str, body: Any) -> httpx.Response:
            with httpx.Client(base_url=base_url, timeout=60) as http:
                barrier.wait()
                started = time.perf_counter()
                response = http.request(method, path, json=body, headers=player.headers)
                elapsed = (time.perf_counter() - started) * 1000
            try:
                received: Any = response.json()
            except ValueError:
                received = response.text[:300]
            self.transcript.add(Exchange(
                who=player.name, method=method, path=f"{path} [concurrent]",
                status=response.status_code, elapsed_ms=elapsed, sent=body,
                received=received,
            ))
            return response

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            responses = list(pool.map(lambda r: fire(*r), requests))
        errors = [r for r in responses if r.status_code >= 500]
        if errors:
            raise ServerError(
                f"{len(errors)} of {len(responses)} concurrent requests failed: "
                f"{errors[0].status_code} {errors[0].text[:300]}"
            )
        return responses

    def grant(self, player: Player) -> None:
        response = self.webhook("new_digital_product", player)
        if response.status_code != 200 or response.json().get("action") != "grant":
            raise HarnessError(f"could not grant access to {player}: {response.text}")

    def revoke(self, player: Player) -> None:
        response = self.webhook("refund", player)
        if response.status_code != 200 or response.json().get("action") != "revoke":
            raise HarnessError(f"could not revoke access of {player}: {response.text}")
