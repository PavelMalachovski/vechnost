"""Couple mode: two phones, one deck, taking turns.

Rooms live in the database and clients poll for state, and card texts are
served from here (localized per requester), so one payment covers both
partners: an unpaid guest sees every card of a paid creator's room.

A room nobody in it has paid for holds the free preview. It stays that way
only while that is true: the moment either player has access - bought before
joining or in the middle of the game - the rest of the deck is dealt in after
the cards already there, for both of them. It used to be decided once, by the
creator, at creation, so a paying guest sat through an unpaid creator's five
cards and a payment made mid-game changed nothing (backend audit B-20).
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import analytics, invites
from ..config import settings
from ..freemium import FREE_CARDS_PER_DECK
from ..i18n import Language
from ..logic import localized_game_data
from ..models import ContentType, Theme
from . import partner_notify, partners
from .database import get_db
from .repositories import RoomRepository
from .services import user_has_access
from .throttle import throttle
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

ROOM_TTL = timedelta(hours=24)


class CreateRoomRequest(BaseModel):
    theme: str
    # Bounded: the column is an INTEGER, and 99999999999 for a deck without
    # levels was ignored when picking the cards and then overflowed int32 on
    # PostgreSQL - a 500. Three levels exist; ten leaves room for more.
    level: int | None = Field(default=None, ge=1, le=10)
    type: str = Field(default="questions", pattern="^(questions|tasks)$")


def _generate_room_code() -> str:
    """A fresh code, from the one generator in `invites`."""
    return invites.new_code()


def _identity(authorization: str | None, guest_id: str | None) -> tuple[int, str]:
    """
    Resolve the caller to a stable (user_id, name).

    Real users authenticate with Mini App initData. When payments are
    disabled (local development, browser preview) an X-Guest-Id header
    provides a stable pseudo-identity instead.
    """
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() == "tma" and init_data:
        try:
            parsed = validate_init_data(init_data, settings.telegram_bot_token)
            user = parsed["user"]
            return int(user["id"]), user.get("first_name") or "Player"
        except InitDataError as e:
            logger.warning(f"Room request initData rejected: {e}")
            raise HTTPException(status_code=401, detail="unauthorized") from e

    if not settings.enable_payment and guest_id:
        # Stable fake id derived from the client-supplied guest id. Hash the
        # whole id — truncating it made any two ids sharing a prefix
        # ("alice-device"/"alice-phone") the same player.
        digest = hashlib.blake2b(guest_id.encode(), digest_size=6).digest()
        return int.from_bytes(digest, "big"), "Player"

    raise HTTPException(status_code=401, detail="unauthorized")


def _room_items(room, language: Language) -> list:
    try:
        theme = Theme(room.theme)
        content_type = ContentType(room.content_type)
    except ValueError as e:
        raise HTTPException(status_code=410, detail="room content is gone") from e
    return localized_game_data.get_content(theme, room.level, content_type, language) or []


def _is_adult(room) -> bool:
    """Whether the room's deck is 18+ (the Sex deck), as the Mini App marks it."""
    try:
        return localized_game_data.has_nsfw_content(Theme(room.theme))
    except ValueError:
        return False


def _seats(room) -> tuple[int, ...]:
    """Who sits in the room: the creator, and the guest once there is one."""
    return tuple(
        user_id
        for user_id in (room.creator_telegram_user_id, room.guest_telegram_user_id)
        if user_id is not None
    )


async def _anyone_paid(seats: tuple[int, ...]) -> bool:
    """Whether either player may see the whole deck.

    Asked only about a room that holds less than its deck, so a paid room's
    poll costs nothing extra. Each player's access is `user_has_access`,
    the one rule, asked outside any session the caller holds open.
    """
    if not settings.enable_payment:
        return True
    for user_id in seats:
        if await user_has_access(user_id):
            return True
    return False


def _deal_the_rest(room, deck_size: int) -> bool:
    """Grow a room holding part of its deck to all of it. True if it grew.

    Every card already in the room keeps its place - the ones shown, the
    one on the table, the free ones still to come - and the rest of the deck
    is shuffled in after them, so nothing either phone has seen moves. A
    room that finished on its last free card carries on from the next one:
    the tap that finished it was spent, so the turn it passed stays passed,
    exactly as if the deck had been whole when it was made.
    """
    order = list(room.card_order or [])
    if len(order) >= deck_size:
        return False
    dealt = set(order)
    rest = [index for index in range(deck_size) if index not in dealt]
    random.shuffle(rest)
    room.card_order = order + rest
    if room.finished:
        room.finished = False
        room.idx += 1
    room.updated_at = datetime.utcnow()
    return True


def _room_state(room, user_id: int, language: Language) -> dict[str, Any]:
    """Serialize room state for one player, card text in their language."""
    items = _room_items(room, language)
    order = room.card_order or []
    total = len(order)
    idx = min(room.idx, total - 1) if total else 0
    card_index = order[idx] if total else 0
    card_text = items[card_index] if card_index < len(items) else ""

    is_creator = user_id == room.creator_telegram_user_id
    turn_holder = room.creator_telegram_user_id if room.turn == 0 else room.guest_telegram_user_id
    turn_name = room.creator_name if room.turn == 0 else room.guest_name

    return {
        "code": room.code,
        "theme": room.theme,
        "level": room.level,
        "type": room.content_type,
        "idx": idx,
        "total": total,
        # The deck in full, and whether this room holds less of it - the free
        # preview, nobody in the room having paid. At its last card the app
        # offers the rest instead of congratulating the pair on a finished
        # deck, and says how much there is.
        "full_total": len(items),
        "trimmed": total < len(items),
        "nsfw": _is_adult(room),
        "card_index": card_index,
        "card_text": card_text,
        "finished": room.finished,
        "started": room.guest_telegram_user_id is not None,
        "your_role": "creator" if is_creator else "guest",
        "your_turn": (
            not room.finished and room.guest_telegram_user_id is not None and turn_holder == user_id
        ),
        "turn_name": turn_name,
        "players": {
            "creator": room.creator_name,
            "guest": room.guest_name,
        },
        # See compat_api._state: the invite is a link, and the server spells
        # it, so all three two-partner features send the same shape.
        "invite_url": invites.invite_url("duo", room.code),
    }


async def _load_room(session, code: str, *, member: int | None = None, for_update: bool = False):
    """The room behind a code, or 404/410.

    With `member`, anyone who is not sitting in the room gets the 404 an
    unknown code gets, and gets it before the TTL is looked at: a 410 for a
    stranger said "this code was real", which is exactly what the uniform
    404 exists not to say. Join passes no member - whoever holds the link
    may take the empty seat - and is throttled for that reason.

    `for_update` takes a row lock, which /advance needs: it reads idx and
    turn and writes both back, and a double tap is two of those at once.
    Opening a room up after a payment needs it for the same reason: both
    phones poll, and each would deal its own shuffle of the rest.
    """
    code = code.strip().upper()
    # A code that could never have been minted is the same 404 as an unknown
    # one, and never reaches the database: a NUL byte in a text parameter
    # is a 500 on PostgreSQL.
    room = (
        await RoomRepository.get_by_code(session, code, for_update=for_update)
        if invites.valid_code(code)
        else None
    )
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    if member is not None and member not in (
        room.creator_telegram_user_id,
        room.guest_telegram_user_id,
    ):
        raise HTTPException(status_code=404, detail="room not found")
    if datetime.utcnow() - room.updated_at > ROOM_TTL:
        raise HTTPException(status_code=410, detail="room expired")
    return room


def _language(lang: str) -> Language:
    return Language.coerce(lang)


async def _opened(code: str, user_id: int, language: Language) -> dict[str, Any]:
    """Deal the rest of the deck into the room, under the row lock.

    Called once a poll, a join or a tap has found the room holding part of
    its deck and a player in it with access. Both phones poll, so both find
    that; the lock makes the second wait for the first, and the second then
    finds the deck whole and changes nothing. Without it each dealt its own
    shuffle of the rest and the two phones were shown different cards.
    """
    async with get_db() as session:
        room = await _load_room(session, code, member=user_id, for_update=True)
        if _deal_the_rest(room, len(_room_items(room, language))):
            await session.flush()
            logger.info(f"Room #{room.id}: a player has access, the whole deck is in")
        return _room_state(room, user_id, language)


@router.post("", dependencies=[Depends(throttle("create"))])
async def create_room(
    body: CreateRoomRequest,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _identity(authorization, x_guest_id)
    language = _language(lang)

    try:
        theme = Theme(body.theme)
        content_type = ContentType(body.type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="unknown deck") from e

    items = localized_game_data.get_content(theme, body.level, content_type, language)
    if not items:
        raise HTTPException(status_code=404, detail="unknown deck")

    # The creator's access decides the deck the room starts with: paid
    # creators share the full deck with their partner, unpaid ones the free
    # preview - until either of them has access, when the rest is dealt in.
    paid = not settings.enable_payment or await user_has_access(user_id)
    size = len(items) if paid else min(FREE_CARDS_PER_DECK, len(items))
    order = list(range(size))
    random.shuffle(order)

    async with get_db() as session:
        code = _generate_room_code()
        while await RoomRepository.get_by_code(session, code):
            code = _generate_room_code()
        room = await RoomRepository.create(
            session,
            code=code,
            creator_telegram_user_id=user_id,
            creator_name=name,
            theme=theme.value,
            level=body.level,
            content_type=content_type.value,
            card_order=order,
        )
        analytics.record(session, "room_create", user_id)
        return _room_state(room, user_id, language)


@router.post("/{code}/join", dependencies=[Depends(throttle("join"))])
async def join_room(
    code: str,
    background: BackgroundTasks,
    lang: str = "ru",
    nsfw: int = 0,
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _identity(authorization, x_guest_id)
    language = _language(lang)
    seated: partners.Seated | None = None

    async with get_db() as session:
        room = await _load_room(session, code)
        if room.creator_telegram_user_id == user_id:
            pass  # creator re-opening their own room
        elif room.guest_telegram_user_id is None:
            if nsfw != 1 and _is_adult(room):
                # The seat stays empty until whoever opened the link has said
                # they are 18: the app asks, and sends `nsfw=1` - the same
                # client-asserted gate as the Library's. Seating them first
                # and asking after meant a partner who said no still sat in
                # the room, and the creator played on alone.
                raise HTTPException(status_code=403, detail="18+ deck: confirm age first")
            # One conditional UPDATE, not a read followed by a write: two
            # people opening the link at once must not both be seated with
            # the last writer silently displacing the first.
            await RoomRepository.seat_guest(session, room, user_id, name)
            if room.guest_telegram_user_id != user_id:
                raise HTTPException(status_code=409, detail="room is full")
            analytics.record(session, "room_join", user_id)
            seated = await partners.seat_taken(
                session,
                screen="coop",
                code=room.code,
                creator_id=room.creator_telegram_user_id,
                creator_name=room.creator_name,
                guest_id=user_id,
                guest_name=name,
            )
        elif room.guest_telegram_user_id != user_id:
            raise HTTPException(status_code=409, detail="room is full")
        state = _room_state(room, user_id, language)
        seats = _seats(room)

    # After the commit, and after the answer: see partner_notify.
    if seated is not None:
        background.add_task(partner_notify.notify_partner_joined, seated)

    # A paying guest in an unpaid creator's room: the rest of the deck is
    # theirs to share, from the first card.
    if state["trimmed"] and await _anyone_paid(seats):
        return await _opened(code, user_id, language)
    return state


@router.get("/{code}")
async def get_room(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _identity(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        # A stranger gets 404, not 403: they must not learn the code is live.
        room = await _load_room(session, code, member=user_id)
        state = _room_state(room, user_id, language)
        seats = _seats(room)

    # The poll is how a payment reaches the room: whoever paid, and whenever,
    # the next poll from either phone finds it and opens the deck for both.
    if state["trimmed"] and await _anyone_paid(seats):
        return await _opened(code, user_id, language)
    return state


@router.post("/{code}/advance", dependencies=[Depends(throttle("write"))])
async def advance_room(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _identity(authorization, x_guest_id)
    language = _language(lang)

    # Whether a payment has opened the rest of the deck is settled before the
    # row is locked: access lives in other tables, behind a session of its
    # own, and nothing should hold the partner's poll up while it is asked.
    async with get_db() as session:
        room = await _load_room(session, code, member=user_id)
        trimmed = len(room.card_order or []) < len(_room_items(room, language))
        seats = _seats(room)
    opened = trimmed and await _anyone_paid(seats)

    async with get_db() as session:
        # Locked: a double tap is two read-modify-writes of idx and turn at
        # once, and without the lock both were accepted - five 200s for one
        # card on PostgreSQL, and a straggling tap could undo the partner's.
        room = await _load_room(session, code, member=user_id, for_update=True)
        if opened:
            # Before the move, so the tap on the last free card turns up the
            # next one instead of finishing a deck that is no longer short.
            _deal_the_rest(room, len(_room_items(room, language)))
        if room.guest_telegram_user_id is None:
            raise HTTPException(status_code=409, detail="partner has not joined yet")
        if room.finished:
            raise HTTPException(status_code=409, detail="deck is finished")

        turn_holder = (
            room.creator_telegram_user_id if room.turn == 0 else room.guest_telegram_user_id
        )
        if turn_holder != user_id:
            raise HTTPException(status_code=403, detail="not your turn")

        if room.idx + 1 >= len(room.card_order or []):
            room.finished = True
        else:
            room.idx += 1
        room.turn = 1 - room.turn
        room.updated_at = datetime.utcnow()
        await session.flush()
        return _room_state(room, user_id, language)
