"""Request throttling for the public HTTP surface.

Three of the endpoints here are worth spending an attacker's time on, and
none of them cost the attacker anything today:

* joining a room, a compatibility test or a game by code. The code is six
  characters of a 32-symbol alphabet, and a hit hands over a paid deck or a
  couple's answers about their sex life. Guessing is the whole attack.
* rendering a share card. Every request composites a JPEG through Pillow,
  so a laptop can saturate the box.
* the admin token. Unlimited guesses turn a shared secret into a countdown.

The window is in-process on purpose: the bot and the web server run in one
process (`run_webhook.py`), so one process is the whole deployment. Run
several workers and each keeps its own counters, which multiplies every
limit below by the worker count. That is a weaker guarantee, not a broken
one, and the fix is a shared store rather than a different shape of code.

The client key is the forwarded address when there is one, because behind a
platform proxy every request otherwise looks like the proxy. That header is
client-settable, so a single attacker who rotates it evades their own
per-client budget. `GLOBAL` exists for exactly that case: code guessing is
also capped across all clients at once, so the keyspace cannot be swept
quickly by anyone, spoofed or not.
"""

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Attempts allowed per window, per client, keyed by bucket name.
LIMITS: dict[str, tuple[int, int]] = {
    # (max attempts, window seconds)
    "join": (10, 300),      # guessing someone else's code
    "create": (20, 3600),   # spinning up rooms/tests/games
    "render": (30, 60),     # /api/card, one Pillow composite each
    "admin": (5, 60),       # the admin bearer token
    "write": (120, 60),     # ordinary in-game writes: dice, answers, reactions
}

# Ceilings applied across every client at once. Only the buckets where a
# single success is worth a lot to a stranger need one; ordinary gameplay
# writes are supposed to scale with the number of couples playing.
GLOBAL_LIMITS: dict[str, tuple[int, int]] = {
    "join": (600, 300),
    "admin": (30, 60),
}

_hits: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(deque))
_global_hits: dict[str, deque[float]] = defaultdict(deque)

# Left unbounded, `_hits` grows one deque per distinct client key forever.
_SWEEP_EVERY = 500
_calls_since_sweep = 0


def client_key(request: Request) -> str:
    """A stable-enough identity for one caller."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry is the original client; the rest are proxies.
        return forwarded.split(",")[0].strip()
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
