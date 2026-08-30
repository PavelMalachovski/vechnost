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

Each partner has their own piece and walks their own board. A player who
reaches 69 stops rolling and waits; the finale unlocks when both are home.
Secrets and Joker tasks are not in the board payload: a cell's instruction
reaches the player standing on it through `steps69.cell_view`, and their
partner gets only the one line written for them.
"""

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import invites, steps69
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

# The four suits the deck already uses, so a piece on the board belongs to
# the same world as the cards. Both partners must pick different ones.
PIECES = ("hearts", "spades", "clubs", "diamonds")

Seat = Literal[0, 1]


class CreateRequest(BaseModel):
    mode: Literal["duo", "solo"] = "duo"
    piece: str = Field(default="hearts")


class JoinRequest(BaseModel):
    # Optional, and normally absent: a partner arriving through an invite
    # link has not been past the suit picker, so the server deals them a free
    # suit. It used to default to a suit, and both ends defaulted to the same
    # one, so the ordinary case — neither partner touching the picker — was a
    # 409 that read as "the game will not let me in".
    piece: str | None = None


class FinaleRequest(BaseModel):
    choice: str = Field(min_length=1, max_length=32)


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def _language(lang: str) -> Language:
    return Language.coerce(lang)


def _validated_piece(piece: str, taken: str | None) -> str:
    """A suit nobody else in this game is already wearing."""
    if piece not in PIECES:
        raise HTTPException(status_code=400, detail="unknown piece")
    if taken is not None and piece == taken:
        raise HTTPException(status_code=409, detail="piece already taken")
    return piece


def _free_piece(piece: str | None, taken: str | None) -> str:
    """The suit the joining partner ends up wearing.

    A suit that is free is granted; anything else — none asked for, an
    unknown one, or the one the creator is already wearing — is swapped for
    the first free suit rather than refused. Which of four glyphs a piece
    wears is not worth a locked door, and the door was locked by default:
    both ends sent "hearts" unless someone thought to change it.
    """
    if piece in PIECES and piece != taken:
        return piece
    return next(p for p in PIECES if p != taken)


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


def _position(game: Steps69Game, seat: int) -> int:
    return game.creator_position if seat == 0 else game.guest_position


def _set_position(game: Steps69Game, seat: int, value: int) -> None:
    if seat == 0:
        game.creator_position = value
    else:
        game.guest_position = value


def _rolls(game: Steps69Game, seat: int) -> int:
    return game.creator_turns if seat == 0 else game.guest_turns


def _piece(game: Steps69Game, seat: int) -> str | None:
    return game.creator_piece if seat == 0 else game.guest_piece


def _joker_id(game: Steps69Game, seat: int) -> str | None:
    return game.creator_joker_task_id if seat == 0 else game.guest_joker_task_id


def _home(game: Steps69Game, seat: int) -> bool:
    return _position(game, seat) >= steps69.BOARD_SIZE


def _both_home(game: Steps69Game) -> bool:
    return _home(game, 0) and _home(game, 1)


def _player_view(
    game: Steps69Game, seat: int, audience: steps69.Audience, language: Language
) -> dict[str, Any]:
    """One player as the caller may see them: where they stand and on what."""
    return {
        "seat": seat,
        "name": game.creator_name if seat == 0 else game.guest_name,
        "piece": _piece(game, seat),
        "position": _position(game, seat),
        "rolls": _rolls(game, seat),
        "home": _home(game, seat),
        "cell": steps69.cell_view(
            _position(game, seat),
            audience,
            joker_task_id=_joker_id(game, seat),
            language=language,
        ),
    }


def _state(
    game: Steps69Game, user_id: int, language: Language
) -> dict[str, Any]:
    """The game as one caller may see it."""
    solo = game.mode == "solo"
    started = solo or game.guest_telegram_user_id is not None
    seat = _seat(game, user_id)

    # One phone shows the seat that just *moved*, and shows it everything:
    # there is no second device to withhold a secret from. The mover, not
    # the next player — the card is the task they were just dealt, and
    # switching to the next player's card the instant the dice landed meant
    # nobody ever read their own. Before the first roll there is no mover,
    # so the seat on turn stands in.
    #
    # Two phones each show their own piece, and see only the partner's line
    # on the other.
    me = (game.last_seat if game.last_seat is not None else game.turn) if solo else seat
    them = 1 - me

    state: dict[str, Any] = {
        "code": game.code,
        "mode": game.mode,
        "your_role": "creator" if seat == 0 else "guest",
        "your_seat": seat,
        "started": started,
        "finished": game.finished,
        "turn": game.turn,
        "your_turn": (
            not game.finished
            and started
            and (solo or game.turn == seat)
            and not _home(game, game.turn)
        ),
        "turn_name": game.creator_name if game.turn == 0 else game.guest_name,
        "you": _player_view(game, me, "shared" if solo else "mover", language),
        "partner": _player_view(game, them, "shared" if solo else "partner", language),
        "both_home": _both_home(game),
        "finale": (
            steps69.load_finale(language).model_dump() if _both_home(game) else None
        ),
        "finale_choice": game.finale_choice,
        "pieces_taken": [p for p in (game.creator_piece, game.guest_piece) if p],
        # The link the creator sends. Composed here rather than in the client
        # so the app never has to know how a deep link is spelled, and so the
        # shape follows the deployment's own configuration.
        "invite_url": invites.invite_url("s69", game.code),
    }

    if game.last_seat is not None:
        state["last"] = {
            "seat": game.last_seat,
            "from": game.last_from,
            "roll": game.last_roll,
            "landed": game.last_landed,
            "to": _position(game, game.last_seat),
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

@router.get("/pieces")
async def pieces() -> dict[str, Any]:
    """The suits a player may choose. Public: it is four words."""
    return {"pieces": list(PIECES)}


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
    piece = _validated_piece(body.piece, None)

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
            creator_piece=piece,
        )
        if body.mode == "solo":
            # One phone, two players: the second seat exists but nobody
            # authenticates into it, so it gets the first free suit.
            game.guest_piece = next(p for p in PIECES if p != piece)
            game.guest_name = game.guest_name or None
            await session.flush()
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
    body: JoinRequest,
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
            game.guest_piece = _free_piece(body.piece, game.creator_piece)
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
        # Locked: a roll reads a position, a roll count and the spent-joker
        # list and writes all three back, and both partners poll the same row.
        game = await _load(session, code, user_id, for_update=True)

        if game.finished:
            raise HTTPException(status_code=409, detail="the game is over")

        solo = game.mode == "solo"
        if solo:
            mover = game.turn
        else:
            if game.guest_telegram_user_id is None:
                raise HTTPException(status_code=409, detail="partner has not joined yet")
            mover = _seat(game, user_id)
            if game.turn != mover:
                raise HTTPException(status_code=403, detail="not your turn")

        if _home(game, mover):
            # Cell 69 blocks that piece for the rest of the game; the pair
            # leave the board by choosing a finale, not by rolling past it.
            raise HTTPException(status_code=409, detail="the dice are done")

        move = steps69.resolve_move(
            _position(game, mover), steps69.roll_dice(), language
        )

        game.last_seat = mover
        game.last_from = move.start
        game.last_roll = move.roll
        game.last_landed = move.landed
        game.last_event = move.event
        _set_position(game, mover, move.position)
        if mover == 0:
            game.creator_turns += 1
        else:
            game.guest_turns += 1

        landed_cell = steps69.cell(move.position, language)
        joker_id = None
        if landed_cell.kind == "joker":
            spent = list(game.used_jokers or [])
            task = steps69.pick_joker(
                move.position, _rolls(game, mover), used=spent, language=language
            )
            joker_id = task.id
            if task.id not in spent:
                spent.append(task.id)
            game.used_jokers = spent
        if mover == 0:
            game.creator_joker_task_id = joker_id
        else:
            game.guest_joker_task_id = joker_id

        # The turn passes to the partner unless they are already home, in
        # which case the mover keeps rolling until they are home too.
        other = 1 - mover
        game.turn = other if not _home(game, other) else mover

        game.updated_at = datetime.utcnow()
        # A pair who come back and finish should be eligible for a nudge
        # again if they start another game later.
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
        if not _both_home(game):
            raise HTTPException(status_code=409, detail="both pieces must reach 69")

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


@router.delete("/{code}")
async def delete(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Erase the game. Either participant may do it, finished or not.

    Also what "начать заново" runs: a fresh board is a new game, and leaving
    the old one behind would have `/mine` offer to resume the game the pair
    just abandoned.
    """
    user_id, _ = _caller(authorization, x_guest_id)

    async with get_db() as session:
        game = await _load(session, code, user_id)
        await Steps69Repository.delete(session, game.id)
        logger.info(f"Steps69 game {game.code} deleted by participant")
        return {"deleted": True}
