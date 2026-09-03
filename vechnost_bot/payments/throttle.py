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

The client key is the forwarded address when there is one, because behind a
platform proxy every request otherwise looks like the proxy. The header is
a list the client may start and each proxy appends to, so the entry to
trust is counted from the *right*: `TRUSTED_PROXY_HOPS` proxies in front
of the app means the client is that many entries from the end (one, on
Railway). The first entry - which this used to read - is whatever the
caller wrote, and a caller who rotates it never spends a budget.

`GLOBAL_LIMITS` exists because even the right entry can be forged by a
caller with many addresses: every bucket where a single success is worth
something to a stranger, or where each request costs the box real work, is
also capped across all clients at once.
"""

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request

from ..config import settings

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
}

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

    global_limit = GLOBAL_LIMITS.get(bucket)
    if global_limit:
        gmax, gwindow = global_limit
        gstamps = _global_hits[bucket]
        _prune(gstamps, now, gwindow)
        if len(gstamps) >= gmax:
            logger.warning(f"Throttle: global ceiling hit on '{bucket}'")
            raise HTTPException(status_code=429, detail="too many requests")
        gstamps.append(now)

    stamps = _hits[bucket][key]
    _prune(stamps, now, window)
    if len(stamps) >= limit:
        logger.warning(f"Throttle: '{bucket}' budget spent by {key}")
        raise HTTPException(status_code=429, detail="too many requests")
    stamps.append(now)


def throttle(bucket: str) -> Callable:
    """FastAPI dependency that spends one unit of `bucket` per request."""
    if bucket not in LIMITS:
        raise KeyError(bucket)

    async def dependency(request: Request) -> None:
        check(bucket, client_key(request))

    return dependency


def reset() -> None:
    """Forget every window. For tests, which must not inherit each other."""
    _hits.clear()
    _global_hits.clear()
