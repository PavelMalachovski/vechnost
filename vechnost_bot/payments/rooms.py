"""Couple mode: two phones, one deck, taking turns.

Rooms live in the database and clients poll for state. The room's deck is
capped by the creator's access at creation time, and card texts are served
from here (localized per requester) — so one payment covers both partners,
and an unpaid guest still sees every card of a paid creator's room.
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import invites
from ..config import settings
from ..freemium import FREE_CARDS_PER_DECK
from ..i18n import Language
from ..logic import localized_game_data
from ..models import ContentType, Theme
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
    level: int | None = None
    type: str = Field(default="questions", pattern="^(questions|tasks)$")


def _generate_room_code() -> str:
    """A fresh code, from the one generator in `invites`."""
    return invites.new_code()


def _identity(
    authorization: str | None, guest_id: str | None
) -> tuple[int, str]:
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
    return localized_game_data.get_content(
        theme, room.level, content_type, language
    ) or []


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
        "card_index": card_index,
        "card_text": card_text,
        "finished": room.finished,
        "started": room.guest_telegram_user_id is not None,
        "your_role": "creator" if is_creator else "guest",
        "your_turn": (not room.finished
                      and room.guest_telegram_user_id is not None
                      and turn_holder == user_id),
        "turn_name": turn_name,
        "players": {
            "creator": room.creator_name,
            "guest": room.guest_name,
        },
        # See compat_api._state: the invite is a link, and the server spells
        # it, so all three two-partner features send the same shape.
        "invite_url": invites.invite_url("duo", room.code),
    }


async def _load_room(session, code: str):
    """The room behind a code, or 404/410. Says nothing about membership.

    Took a `user_id` it never looked at, which read like an access check and
    was not one; every caller does its own membership check right after.
    """
    room = await RoomRepository.get_by_code(session, code.strip().upper())
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    if datetime.utcnow() - room.updated_at > ROOM_TTL:
        raise HTTPException(status_code=410, detail="room expired")
    return room


def _language(lang: str) -> Language:
    return Language.coerce(lang)


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

    items = localized_game_data.get_content(
        theme, body.level, content_type, language
    )
    if not items:
        raise HTTPException(status_code=404, detail="unknown deck")

    # The room inherits the creator's access: paid creators share the full
    # deck with their partner, unpaid ones share the free preview.
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
        return _room_state(room, user_id, language)


@router.post("/{code}/join", dependencies=[Depends(throttle("join"))])
async def join_room(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _identity(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        room = await _load_room(session, code)
        if room.creator_telegram_user_id == user_id:
            pass  # creator re-opening their own room
        elif room.guest_telegram_user_id is None:
            room.guest_telegram_user_id = user_id
            room.guest_name = name
            room.updated_at = datetime.utcnow()
            await session.flush()
        elif room.guest_telegram_user_id != user_id:
            raise HTTPException(status_code=409, detail="room is full")
        return _room_state(room, user_id, language)


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
        room = await _load_room(session, code)
        if user_id not in (room.creator_telegram_user_id, room.guest_telegram_user_id):
            raise HTTPException(status_code=403, detail="not a player in this room")
        return _room_state(room, user_id, language)


@router.post("/{code}/advance", dependencies=[Depends(throttle("write"))])
async def advance_room(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _identity(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        room = await _load_room(session, code)
        if user_id not in (room.creator_telegram_user_id, room.guest_telegram_user_id):
            raise HTTPException(status_code=403, detail="not a player in this room")
        if room.guest_telegram_user_id is None:
            raise HTTPException(status_code=409, detail="partner has not joined yet")
        if room.finished:
            raise HTTPException(status_code=409, detail="deck is finished")

        turn_holder = (
            room.creator_telegram_user_id if room.turn == 0
            else room.guest_telegram_user_id
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
