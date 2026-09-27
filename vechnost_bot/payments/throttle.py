"""Request throttling for the public HTTP surface.

Three of the endpoints here are worth spending an attacker's time on, and
none of them cost the attacker anything today:

* joining a room, a compatibility test or a game by code. The code is six
  characters of a 32-symbol alphabet, and a hit hands over a paid deck or a
  couple's answers about their sex life. Guessing is the whole attack.
* rendering a share card. Every request composites a JPEG through Pillow,
  so a laptop can saturate the box.
* the admin token. Unlimited guesses turn a shared secret into a countdown.

The window is in-process on purpose: every throttled endpoint lives in the
single web process (`run_webhook.py` runs the bot beside it as a separate
process, but the bot serves no HTTP), so one process holds every counter.
Run several web workers and each keeps its own counters, which multiplies
every limit below by the worker count. That is a weaker guarantee, not a
broken one, and the fix is a shared store rather than a different shape of
code.

A per-client budget belongs to a person when Telegram vouches for one. The
Mini App signs every request with initData, and on the buckets its
endpoints serve (`BY_PERSON`) a request whose initData validates spends
the budget of that Telegram user. Keyed by address, everyone behind one
mobile carrier's NAT - hundreds of strangers on one public IP - shared a
single `join` and `write` budget, so one of them probing codes, or a busy
evening of dice, turned into 429s for couples who had never met. Now one
person has one budget on every network, and a stranger on the same
address cannot spend it. A request whose initData does not validate is
budgeted by its address, so nobody spends someone else's budget by
claiming their id.

Everything else is keyed by address: anonymous requests, the Tribute
webhook and the admin routes, which do not authenticate by initData. The
address is the forwarded one when there is one, because behind a platform
proxy every request otherwise looks like the proxy. The header is a list
the client may start and each proxy appends to, so the entry to trust is
counted from the *right*: `TRUSTED_PROXY_HOPS` proxies in front of the app
means the client is that many entries from the end (one, on Railway). The
first entry - which this used to read - is whatever the caller wrote, and a
caller who rotates it never spends a budget.

`GLOBAL_LIMITS` exists because even the right entry can be forged by a
caller with many addresses, or many Telegram accounts: every bucket where a
single success is worth something to a stranger, or where each request
costs the box real work, is also capped across all clients at once.
"""

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request

from ..config import settings
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

# Attempts allowed per window, per client, keyed by bucket name.
LIMITS: dict[str, tuple[int, int]] = {
    # (max attempts, window seconds)
    "join": (10, 300),      # guessing someone else's code
    # Spinning up rooms/tests/games. Sixty an hour, not twenty: this bucket
    # exists to stop someone allocating rows in bulk, and twenty is inside
    # what one curious couple does in an evening - open a board, abandon it,
    # start again, invite the partner, restart when they pick the wrong
    # suit. Hitting it looked like the game was broken, because a 429 was
    # not one of the statuses the client had a sentence for.
    "create": (60, 3600),
    "render": (30, 60),     # /api/card, one Pillow composite each
    "admin": (5, 60),       # the admin bearer token
    "write": (120, 60),     # ordinary in-game writes: dice, answers, reactions
    # Tribute delivers a handful of events a day and retries a failed one
    # with backoff, so this is far above anything legitimate. What it caps
    # is a stranger making the box hash and HMAC 64 KB bodies all day.
    "webhook": (60, 60),
    # What the Mini App counts: a few dozen in an evening of play, an
    # arrival once a day. A cap on filling the events table, not a budget
    # anyone playing will meet.
    "events": (300, 600),
}

# Buckets whose endpoints authenticate the caller by Telegram initData, and
# so may budget the person rather than the address. Not "admin" or
# "webhook": neither is a Mini App request, and a budget there must not be
# something a caller can pick by attaching initData of their own.
BY_PERSON = frozenset({"create", "join", "write", "render", "events"})

# Ceilings applied across every client at once. Only the buckets where a
# single success is worth a lot to a stranger need one; ordinary gameplay
# writes are supposed to scale with the number of couples playing.
GLOBAL_LIMITS: dict[str, tuple[int, int]] = {
    "join": (600, 300),
    "admin": (30, 60),
    "webhook": (600, 60),
    # Each render is a Pillow composite; ten a second across everyone is a
    # quarter of a core, and the cache in `renderer.render_card_bytes` means
    # legitimate traffic rarely gets near it.
    "render": (600, 60),
    # Thirty rooms, tests or boards a minute across all couples, which is
    # far above an evening's worth and far below what fills a table.
    "create": (1800, 3600),
    # Every phone's counts together: far above what couples produce, far
    # below what fills a disk.
    "events": (60000, 600),
    # Fifty in-game writes a second across everyone.
    "write": (3000, 60),
}

_hits: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(deque))
_global_hits: dict[str, deque[float]] = defaultdict(deque)

# Left unbounded, `_hits` grows one deque per distinct client key forever.
_SWEEP_EVERY = 500
_calls_since_sweep = 0


def client_key(request: Request) -> str:
    """A stable-enough identity for one caller.

    `X-Forwarded-For` reads `client, proxy1, proxy2, ...` and each proxy
    appends the address it saw. The last `TRUSTED_PROXY_HOPS` entries were
    written by proxies this deployment trusts, so the client is the entry
    just before them; anything further left was written by the client
    itself and is worth nothing.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
        if entries:
            hops = settings.trusted_proxy_hops
            # One trusted proxy that *appends* gives `..., client`; one that
            # *replaces* the header gives just `client`. Both land here.
            index = max(len(entries) - hops, 0)
            return entries[index]
    return request.client.host if request.client else "unknown"


def telegram_user_key(request: Request) -> str | None:
    """`tg:<id>` when the request carries initData that validates, else None."""
    scheme, _, init_data = (request.headers.get("authorization") or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return None
    try:
        parsed = validate_init_data(init_data, settings.telegram_bot_token)
        return f"tg:{int(parsed['user']['id'])}"
    except (InitDataError, KeyError, TypeError, ValueError, OverflowError):
        return None


def caller_key(request: Request, bucket: str) -> str:
    """Whose budget one request spends: the person if known, else the address."""
    if bucket in BY_PERSON:
        person = telegram_user_key(request)
        if person is not None:
            return person
    return client_key(request)


def _prune(stamps: deque[float], now: float, window: int) -> None:
    while stamps and now - stamps[0] > window:
        stamps.popleft()


def _sweep(now: float) -> None:
    """Drop client keys with nothing left inside their window."""
    for bucket, clients in list(_hits.items()):
        window = LIMITS[bucket][1]
        for key, stamps in list(clients.items()):
            _prune(stamps, now, window)
            if not stamps:
                del clients[key]


def check(bucket: str, key: str) -> None:
    """Record one attempt, raising 429 once the budget is spent."""
    global _calls_since_sweep

    limit, window = LIMITS[bucket]
    now = time.monotonic()

    _calls_since_sweep += 1
    if _calls_since_sweep >= _SWEEP_EVERY:
        _calls_since_sweep = 0
        _sweep(now)

    # The client's own budget first, and an attempt is counted only once it
    # is let through. This used to stamp the global window before looking at
    # the client's, so requests the per-client limit had already refused
    # still spent everyone's ceiling: one address that never rotated its
    # X-Forwarded-For, at ~2 requests a second, locked every couple out of
    # joining, and at ~10 a second out of paying (backend audit B-03).
    stamps = _hits[bucket][key]
    _prune(stamps, now, window)
    if len(stamps) >= limit:
        logger.warning(f"Throttle: '{bucket}' budget spent by {key}")
        raise HTTPException(status_code=429, detail="too many requests")

    global_limit = GLOBAL_LIMITS.get(bucket)
    if global_limit:
        gmax, gwindow = global_limit
        gstamps = _global_hits[bucket]
        _prune(gstamps, now, gwindow)
        if len(gstamps) >= gmax:
            logger.warning(f"Throttle: global ceiling hit on '{bucket}'")
            raise HTTPException(status_code=429, detail="too many requests")
        gstamps.append(now)
    stamps.append(now)


def throttle(bucket: str) -> Callable:
    """FastAPI dependency that spends one unit of `bucket` per request."""
    if bucket not in LIMITS:
        raise KeyError(bucket)

    async def dependency(request: Request) -> None:
        check(bucket, caller_key(request, bucket))

    return dependency


def reset() -> None:
    """Forget every window. For tests, which must not inherit each other."""
    _hits.clear()
    _global_hits.clear()
