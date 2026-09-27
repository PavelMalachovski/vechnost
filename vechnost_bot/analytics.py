"""What people do, counted - never what they said.

VECHNOST could not answer one question about its own growth: where people
come from, how many of them play, how many reach a paywall, how many pay.
This module is the one way anything is written down for that, and it is
narrow on purpose:

- **An event is a name and one token.** The name comes from `EVENTS`; the
  token (`detail`) is one value from that event's own allow-list - a door, a
  deck, a Library module - or nothing. There is no free text anywhere: no
  answers, no card texts, no names, and no codes, because a room code is a
  seat in a stranger's game. A value that is not on the list is dropped, not
  stored.
- **A source is first touch.** `src_<tag>` in a bot link or a Mini App link
  names the channel a person came from (`tiktok`, `blogger_anna`); a
  referral, an invite and a gift certificate name themselves. Whatever the
  first event of a person carries is where they came from.
- **Never in the way.** `track` opens its own session and swallows every
  error: a counter must not cost anyone a card, a payment or a reply.
- **Forgotten with the person.** `/delete_me` erases every event of the
  user (`UserRepository.erase`), and the retention sweep drops everything
  older than `KEEP`.

Deliberately imports neither FastAPI nor python-telegram-bot, like
`library.py` and `compat.py`: the bot, the web process and the tests all
call it directly.
"""

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from .library import MODULES
from .models import ContentType, Theme

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .payments.models import AnalyticsEvent

logger = logging.getLogger(__name__)

# Long enough for a year-on-year look, short enough not to be forever.
KEEP = timedelta(days=400)

# The doors a paywall stands in (`showPaywall` in webapp/index.html).
DOORS = frozenset({"deck", "room", "compat", "s69", "library", "guide"})
# The three two-partner features, by the prefix their invite links carry.
INVITE_KINDS = frozenset({"duo", "cmp", "s69"})
# Where the Mini App offers a gift from.
GIFT_DOORS = frozenset({"home", "paywall"})
# How a person reached the bot or the app when no `src_` tag says so; an
# arrival stores one of these as its `source` (see `arrival_source`).
VIA = frozenset({"ref", "invite", "gift", "push"})
# The two arrivals. First touch is the source on a person's first one.
ARRIVALS = frozenset({"bot_start", "app_open"})
# What counts as having played: opening something, or sitting down with a
# partner. /stats calls a newcomer activated by one of these on day one.
ACTIVATIONS = frozenset({
    "deck_open", "lib_open", "room_create", "room_join", "compat_create",
    "compat_join", "s69_create", "s69_join",
})
# A partner taking the second seat: a room, a test, a board.
JOINS = frozenset({"room_join", "compat_join", "s69_join"})


def _decks() -> frozenset[str]:
    """Every deck a person can open, as `theme:level:type`."""
    decks = set()
    for theme in Theme:
        for level in ("", "1", "2", "3"):
            for kind in ContentType:
                decks.add(f"{theme.value}:{level}:{kind.value}")
    return frozenset(decks)


DECKS = _decks()

# name -> the details it may carry (None: it carries none).
EVENTS: dict[str, frozenset[str] | None] = {
    # Arrival. The channel rides in `source`, not in `detail`.
    "bot_start": None,
    "app_open": None,
    # Playing, alone or together.
    "deck_open": DECKS,
    "lib_open": frozenset(MODULES),
    "invite_share": INVITE_KINDS,
    # The app asked for permission to message (requestWriteAccess), and
    # which way it went.
    "write_access": frozenset({"granted", "declined"}),
    # The gift sheet opened, and «Купить сертификат» pressed, by where from.
    "gift_view": GIFT_DOORS,
    "gift_click": GIFT_DOORS,
    "room_create": None,
    "room_join": None,
    "compat_create": None,
    "compat_join": None,
    "compat_done": None,
    "s69_create": frozenset({"solo", "duo"}),
    "s69_join": None,
    # Money.
    "paywall_view": DOORS,
    "buy_click": DOORS,
    "purchase": frozenset({"lifetime", "period"}),
    "gift_purchase": None,
    "refund": None,
}

# What the Mini App may report itself, through POST /api/events. Everything
# else happens on the server and is recorded there, where it cannot be
# forged: a client cannot claim a purchase, a join or a finished test.
CLIENT_EVENTS = frozenset({
    "app_open", "deck_open", "lib_open", "invite_share", "paywall_view", "buy_click",
    "write_access", "gift_view", "gift_click",
})

SOURCE_TAG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SOURCE_PREFIX = "src_"


def clean_source(source: str | None) -> str | None:
    """A source tag as it may be stored, or None."""
    if not source or not isinstance(source, str):
        return None
    tag = source.strip().lower()
    return tag if SOURCE_TAG.match(tag) else None


def parse_source_param(param: str | None) -> str | None:
    """The tag in a `src_<tag>` start parameter, or None."""
    if not isinstance(param, str) or not param.lower().startswith(SOURCE_PREFIX):
        return None
    return clean_source(param[len(SOURCE_PREFIX):])


def arrival_source(param: str | None) -> str | None:
    """The channel a start parameter names: its `src_` tag, or how the
    person came - a referral, an invite, a gift certificate. None is no
    parameter at all, which /stats reports as «без метки»."""
    if not param or not isinstance(param, str):
        return None
    tag = parse_source_param(param)
    if tag:
        return tag
    kind = param.partition("_")[0].lower()
    if kind == "ref":
        return "ref"
    if kind in INVITE_KINDS:
        return "invite"
    if kind == "activate":
        return "gift"
    return None


def clean_detail(name: str, detail: str | None) -> str | None:
    """The detail as it may be stored with `name`, or None.

    Anything not on the event's own list is dropped: a detail is a token
    from a closed set, never text somebody typed.
    """
    allowed = EVENTS.get(name)
    if allowed is None or detail is None:
        return None
    value = str(detail)
    return value if value in allowed else None


def deck_detail(theme: str, level: int | str | None, content_type: str) -> str:
    """The `deck_open` detail for a deck."""
    return f"{theme}:{level or ''}:{content_type}"


def event_row(
    name: str,
    telegram_user_id: int | None,
    detail: str | None = None,
    source: str | None = None,
) -> "AnalyticsEvent | None":
    """The row for one event, or None when the name is not one we count.

    The row is returned unsaved so a caller already holding a session can
    add it to the same transaction as what it records.
    """
    from .payments.models import AnalyticsEvent

    if name not in EVENTS:
        logger.warning(f"Analytics: {name!r} is not an event we count; dropped")
        return None
    return AnalyticsEvent(
        telegram_user_id=telegram_user_id,
        name=name,
        detail=clean_detail(name, detail),
        source=clean_source(source),
    )


def record(
    session: "AsyncSession",
    name: str,
    telegram_user_id: int | None,
    detail: str | None = None,
) -> None:
    """Add one event to a transaction the caller already holds: it commits
    with what it records, or not at all."""
    row = event_row(name, telegram_user_id, detail)
    if row is not None:
        session.add(row)


async def track(
    name: str,
    telegram_user_id: int | None,
    detail: str | None = None,
    source: str | None = None,
) -> None:
    """Record one event in a session of its own. Never raises."""
    row = event_row(name, telegram_user_id, detail, source)
    if row is None:
        return
    try:
        from .payments.database import get_db

        async with get_db() as session:
            session.add(row)
    except Exception as e:
        logger.warning(f"Analytics: {name} not recorded: {type(e).__name__}: {e}")


async def track_arrival(telegram_user_id: int, source: str | None) -> None:
    """Record that a person opened the app - once a UTC day, whatever the
    number of launches, so an arrival counts people and not reloads. Never
    raises."""
    from datetime import datetime

    try:
        from sqlalchemy import select

        from .payments.database import get_db
        from .payments.models import AnalyticsEvent

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        async with get_db() as session:
            seen = await session.scalar(
                select(AnalyticsEvent.id).where(
                    AnalyticsEvent.telegram_user_id == telegram_user_id,
                    AnalyticsEvent.name == "app_open",
                    AnalyticsEvent.created_at >= today,
                ).limit(1)
            )
            if seen is None:
                row = event_row("app_open", telegram_user_id, source=source)
                if row is not None:
                    session.add(row)
    except Exception as e:
        logger.warning(f"Analytics: app_open not recorded: {type(e).__name__}: {e}")
