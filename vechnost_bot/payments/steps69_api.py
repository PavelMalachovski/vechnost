"""«69 ступеней» over HTTP.

Mirrors rooms.py: its own router, its own initData handling, a short code,
both partners polling, and the game inheriting the creator's access so one
payment covers both. Three things differ, and each is deliberate:

* **The whole game is paid.** There is no free prefix, so `create` and
  `board` refuse an unpaid caller outright rather than trimming a payload.
  A guest joining a paid creator's game plays free, exactly as in a room.
* **No TTL.** A pair who stop at cell 45 come back to cell 45. `rooms.py`
  expires after a day because a deck is one sitting; a board is not.
* **The dice are the server's.** The client asks to roll and is told what
  happened. A client that rolled its own dice could roll 69 sixes, and both
  phones have to agree on the same number anyway.

Secrets and Joker tasks are not in the board payload. They reach exactly the
player entitled to them, through `steps69.cell_view`.
"""

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import steps69
from ..config import settings
from ..i18n import Language
from .database import get_db
from .models import Steps69Game
from .repositories import Steps69Repository
from .services import user_has_access
from .throttle import throttle
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/steps69", tags=["steps69"])

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# The emoji a partner may fling across the table. A fixed palette rather
# than free text: whatever lands here is stored and rendered on the other
# partner's phone, and the UI only ever offers these five anyway.
REACTIONS = ("🔥", "❤️", "💦", "😈", "👏")

# How many reactions the row keeps. Enough for a polling client to catch up
# after a few seconds offline, short enough that the column stays small.
REACTION_TAIL = 12


class CreateRequest(BaseModel):
    mode: Literal["duo", "solo"] = "duo"


class FinaleRequest(BaseModel):
    choice: str = Field(min_length=1, max_length=32)


class ReactRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=8)


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def _language(lang: str) -> Language:
    return Language.coerce(lang)


def _caller(authorization: str | None, guest_id: str | None) -> tuple[int, str]:
    """Resolve the caller from initData, or from a guest id when unpaid.

    Same scheme as compat_api.py: the whole guest id is hashed, never a
    prefix, so two ids that merely start alike are two players.
    """
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() == "tma" and init_data:
        try:
            parsed = validate_init_data(init_data, settings.telegram_bot_token)
            user = parsed["user"]
            return int(user["id"]), user.get("first_name") or "Player"
        except InitDataError as e:
            logger.warning(f"Steps69 initData rejected: {e}")
            raise HTTPException(status_code=401, detail="unauthorized") from e

    if not settings.enable_payment and guest_id:
        digest = hashlib.sha256(guest_id.encode()).digest()[:8]
        pseudo = int.from_bytes(digest, "big") & 0x7FFFFFFFFFFFFFFF
        return pseudo, "Player"

    raise HTTPException(status_code=401, detail="unauthorized")


async def _require_access(user_id: int) -> None:
    if settings.enable_payment and not await user_has_access(user_id):
        raise HTTPException(status_code=402, detail="payment required")


async def _load(
    session: AsyncSession, code: str, user_id: int, for_update: bool = False
) -> Steps69Game:
    game = await Steps69Repository.get_by_code(
        session, code.strip().upper(), for_update=for_update
    )
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    if user_id not in (game.creator_telegram_user_id, game.guest_telegram_user_id):
        raise HTTPException(status_code=403, detail="not a player in this game")
    return game


def _seat(game: Steps69Game, user_id: int) -> int:
    """0 for the creator, 1 for the guest."""
    return 0 if user_id == game.creator_telegram_user_id else 1


def _audience(game: Steps69Game, user_id: int) -> steps69.Audience:
    """Which half of a secret cell this caller is entitled to.

    One phone means one screen, so a solo game gets both halves. In a duo
    game the mover is whoever rolled onto the current cell, which is the
    seat opposite the one holding the next turn.
    """
    if game.mode == "solo":
        return "shared"
    if not game.turns:
        # Cell 1 is a joint action and carries no secret; nobody has moved.
        return "shared"
    mover_seat = 1 - game.turn
    return "mover" if _seat(game, user_id) == mover_seat else "partner"


def _state(
    game: Steps69Game, user_id: int, language: Language
) -> dict[str, Any]:
    """The game as one caller may see it."""
    solo = game.mode == "solo"
    started = solo or game.guest_telegram_user_id is not None
    seat = _seat(game, user_id)

    turn_name = game.creator_name if game.turn == 0 else game.guest_name
    your_turn = (
        not game.finished
        and started
        and (solo or game.turn == seat)
        and game.position < steps69.BOARD_SIZE
    )

    state: dict[str, Any] = {
        "code": game.code,
        "mode": game.mode,
        "your_role": "creator" if seat == 0 else "guest",
        "your_seat": seat,
        "started": started,
        "finished": game.finished,
        "position": game.position,
        "turns": game.turns,
        "turn": game.turn,
        "your_turn": your_turn,
        "turn_name": turn_name,
        "players": {"creator": game.creator_name, "guest": game.guest_name},
        "cell": steps69.cell_view(
            game.position,
            _audience(game, user_id),
            joker_task_id=game.joker_task_id,
            language=language,
        ),
        "reactions": list(game.reactions or []),
        "finale_choice": game.finale_choice,
    }

    if game.turns:
        state["last"] = {
            "from": game.last_from,
            "roll": game.last_roll,
            "landed": game.last_landed,
            "to": game.position,
            "event": game.last_event,
            "message": (
                steps69.cell(game.last_landed, language).text
                if game.last_event and game.last_landed
                else None
            ),
        }
    return state


# ---------------------------------------------------------------------------
# Routes. `/mine` is declared before `/{code}` so it is not read as a code.
# ---------------------------------------------------------------------------

@router.post("", dependencies=[Depends(throttle("create"))])
async def create(
    body: CreateRequest,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _caller(authorization, x_guest_id)
    await _require_access(user_id)
    language = _language(lang)

    async with get_db() as session:
        code = _generate_code()
        while await Steps69Repository.get_by_code(session, code):
            code = _generate_code()
        game = await Steps69Repository.create(
            session,
            code=code,
            creator_telegram_user_id=user_id,
            creator_name=name,
            mode=body.mode,
        )
        return _state(game, user_id, language)


@router.get("/mine")
async def mine(
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """The caller's game still in play, so the app can offer to continue it."""
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        game = await Steps69Repository.latest_unfinished_for(session, user_id)
        if not game:
            raise HTTPException(status_code=404, detail="no game in play")
        return _state(game, user_id, language)


@router.post("/{code}/join", dependencies=[Depends(throttle("join"))])
async def join(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Take the second seat. The creator's access covers the guest."""
    user_id, name = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        game = await Steps69Repository.get_by_code(session, code.strip().upper())
        if not game:
            raise HTTPException(status_code=404, detail="game not found")
        if game.mode == "solo":
            raise HTTPException(status_code=409, detail="this game is played on one phone")
        if game.creator_telegram_user_id == user_id:
            pass  # creator re-opening their own game
        elif game.guest_telegram_user_id is None:
            game.guest_telegram_user_id = user_id
            game.guest_name = name
            game.updated_at = datetime.utcnow()
            await session.flush()
        elif game.guest_telegram_user_id != user_id:
            raise HTTPException(status_code=409, detail="game is full")
        return _state(game, user_id, language)


@router.get("/{code}/board")
async def board(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """The map: 69 titles, the portals, the block names.

    Bound to a game and to its players rather than served flat, so the paid
    content is never reachable by anyone who has not been dealt into a game.
    Instructions are not here; they arrive with the square you land on.
    """
    user_id, _ = _caller(authorization, x_guest_id)
    async with get_db() as session:
        await _load(session, code, user_id)
    return steps69.board_view(_language(lang))


@router.get("/{code}")
async def state(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)
    async with get_db() as session:
        return _state(await _load(session, code, user_id), user_id, language)


@router.post("/{code}/roll", dependencies=[Depends(throttle("write"))])
async def roll(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Throw the dice. The server decides the number and where it lands."""
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        # Locked: a roll reads position, turn count and the spent-joker list
        # and writes all three back, and both partners poll the same row.
        game = await _load(session, code, user_id, for_update=True)

        if game.finished:
            raise HTTPException(status_code=409, detail="the game is over")
        if game.position >= steps69.BOARD_SIZE:
            # Cell 69 blocks the dice for the rest of the session; the pair
            # leave it by choosing a finale, not by rolling past it.
            raise HTTPException(status_code=409, detail="the dice are done")

        solo = game.mode == "solo"
        if not solo:
            if game.guest_telegram_user_id is None:
                raise HTTPException(status_code=409, detail="partner has not joined yet")
            if game.turn != _seat(game, user_id):
                raise HTTPException(status_code=403, detail="not your turn")

        move = steps69.resolve_move(
            game.position, steps69.roll_dice(), language
        )

        game.last_from = move.start
        game.last_roll = move.roll
        game.last_landed = move.landed
        game.last_event = move.event
        game.position = move.position
        game.turns += 1
        game.turn = 1 - game.turn

        landed_cell = steps69.cell(move.position, language)
        if landed_cell.kind == "joker":
            spent = list(game.used_jokers or [])
            task = steps69.pick_joker(
                move.position, game.turns, used=spent, language=language
            )
            game.joker_task_id = task.id
            if task.id not in spent:
                spent.append(task.id)
            game.used_jokers = spent
        else:
            game.joker_task_id = None

        game.updated_at = datetime.utcnow()
        # A pair who came back and finished the board should be eligible for
        # a nudge again if they start another game later.
        game.resume_notified_at = None
        await session.flush()
        return _state(game, user_id, language)


@router.post("/{code}/finale", dependencies=[Depends(throttle("write"))])
async def finale(
    code: str,
    body: FinaleRequest,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Choose how cell 69 ends, and close the game for good."""
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        game = await _load(session, code, user_id, for_update=True)
        if game.position < steps69.BOARD_SIZE:
            raise HTTPException(status_code=409, detail="the piece is not on 69 yet")

        valid = {c.id for c in steps69.load_finale(language).choices}
        if body.choice not in valid:
            raise HTTPException(status_code=404, detail="unknown finale")

        if game.finished and game.finale_choice != body.choice:
            # Both partners tap at once; the first choice stands rather than
            # the screen changing under whoever was a moment slower.
            raise HTTPException(status_code=409, detail="the finale is already chosen")

        game.finale_choice = body.choice
        game.finished = True
        game.updated_at = datetime.utcnow()
        await session.flush()
        return _state(game, user_id, language)


@router.post("/{code}/react", dependencies=[Depends(throttle("write"))])
async def react(
    code: str,
    body: ReactRequest,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Send the partner an emoji. Palette only, never free text."""
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    if body.emoji not in REACTIONS:
        raise HTTPException(status_code=400, detail="unknown reaction")

    async with get_db() as session:
        game = await _load(session, code, user_id, for_update=True)
        tail = list(game.reactions or [])
        seq = max((r.get("seq", 0) for r in tail), default=0) + 1
        tail.append({
            "seq": seq,
            "by": "creator" if _seat(game, user_id) == 0 else "guest",
            "emoji": body.emoji,
        })
        game.reactions = tail[-REACTION_TAIL:]
        game.updated_at = datetime.utcnow()
        await session.flush()
        return _state(game, user_id, language)


@router.delete("/{code}")
async def delete(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Erase the game. Either participant may do it, finished or not."""
    user_id, _ = _caller(authorization, x_guest_id)

    async with get_db() as session:
        game = await _load(session, code, user_id)
        await Steps69Repository.delete(session, game.id)
        logger.info(f"Steps69 game {game.code} deleted by participant")
        return {"deleted": True}
