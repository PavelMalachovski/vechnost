"""The couples compatibility test over HTTP.

Mirrors rooms.py: its own router, its own initData handling, access checked
at creation so the creator's payment covers both partners.

No endpoint here ever serializes a partner's answers. State carries counts;
the result carries zones, verdicts and question numbers.
"""

import hashlib
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import invites
from ..compat import TOTAL_QUESTIONS, build_result, load_spheres, scale_labels
from ..compat_notify import notify_result_ready
from ..config import settings
from ..i18n import Language
from .database import get_db
from .repositories import CompatTestRepository
from .services import user_has_access
from .throttle import throttle
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compat", tags=["compat"])


class AnswerRequest(BaseModel):
    index: int = Field(ge=0, lt=TOTAL_QUESTIONS)
    value: int = Field(ge=1, le=5)


def _generate_code() -> str:
    """A fresh code, from the one generator in `invites`."""
    return invites.new_code()


def _language(lang: str) -> Language:
    return Language.coerce(lang)


def _caller(
    authorization: str | None, guest_id: str | None
) -> tuple[int, str]:
    """Resolve the caller from initData, or from a guest id when unpaid.

    Not quite rooms.py's scheme — see the comment on the guest branch below.
    """
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() == "tma" and init_data:
        try:
            parsed = validate_init_data(init_data, settings.telegram_bot_token)
            user = parsed["user"]
            return int(user["id"]), user.get("first_name") or "Player"
        except InitDataError as e:
            logger.warning(f"Compat initData rejected: {e}")
            raise HTTPException(status_code=401, detail="unauthorized") from e

    if not settings.enable_payment and guest_id:
        # Hash the whole guest id rather than truncating to a short prefix
        # (rooms.py's scheme): two distinct guest ids that merely share a
        # prefix must never collapse to the same pseudo user.
        digest = hashlib.sha256(guest_id.encode()).digest()[:8]
        pseudo = int.from_bytes(digest, "big") & 0x7FFFFFFFFFFFFFFF
        return pseudo, "Player"

    raise HTTPException(status_code=401, detail="unauthorized")


async def _load(session, code: str, user_id: int, for_update: bool = False):
    test = await CompatTestRepository.get_by_code(
        session, code.strip().upper(), for_update=for_update
    )
    if not test:
        raise HTTPException(status_code=404, detail="test not found")
    if user_id not in (test.creator_telegram_user_id, test.guest_telegram_user_id):
        raise HTTPException(status_code=403, detail="not a participant in this test")
    return test


def _answered(answers: list) -> int:
    return sum(1 for value in answers if value is not None)


def _state(test, user_id: int) -> dict[str, Any]:
    """State for one caller. Carries counts, never the partner's values."""
    is_creator = user_id == test.creator_telegram_user_id
    mine = test.creator_answers if is_creator else test.guest_answers
    theirs = test.guest_answers if is_creator else test.creator_answers
    return {
        "code": test.code,
        "your_role": "creator" if is_creator else "guest",
        "started": test.guest_telegram_user_id is not None,
        "answered": _answered(mine),
        # Which questions *the caller* has already answered, so the client can
        # resume an interrupted test at the first gap instead of restarting
        # all 40. The caller's own indices only — never the partner's, and
        # never any values, mine or theirs.
        "answered_indices": [i for i, value in enumerate(mine) if value is not None],
        "partner_answered": _answered(theirs),
        "total": TOTAL_QUESTIONS,
        "finished": test.finished_at is not None,
        "players": {"creator": test.creator_name, "guest": test.guest_name},
        # The link that puts the partner straight into this test. Composed
        # server-side so the client never has to know how a deep link is
        # spelled, and so it follows the deployment's own configuration.
        "invite_url": invites.invite_url("cmp", test.code),
    }


@router.get("/questions")
async def questions(lang: str = "ru") -> dict[str, Any]:
    """The questions and the answer scale. No auth: this is public content."""
    language = _language(lang)
    return {
        "scale": scale_labels(language),
        "spheres": [
            {"id": s.id, "title": s.title, "questions": s.questions}
            for s in load_spheres(language)
        ],
        "total": TOTAL_QUESTIONS,
    }


@router.post("", dependencies=[Depends(throttle("create"))])
async def create(
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _caller(authorization, x_guest_id)
    if settings.enable_payment and not await user_has_access(user_id):
        raise HTTPException(status_code=402, detail="payment required")

    async with get_db() as session:
        code = _generate_code()
        while await CompatTestRepository.get_by_code(session, code):
            code = _generate_code()
        test = await CompatTestRepository.create(
            session,
            code=code,
            creator_telegram_user_id=user_id,
            creator_name=name,
        )
        return _state(test, user_id)


@router.post("/{code}/join", dependencies=[Depends(throttle("join"))])
async def join(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _caller(authorization, x_guest_id)

    async with get_db() as session:
        test = await CompatTestRepository.get_by_code(session, code.strip().upper())
        if not test:
            raise HTTPException(status_code=404, detail="test not found")
        if test.creator_telegram_user_id == user_id:
            pass  # creator re-opening their own test
        elif test.guest_telegram_user_id is None:
            test.guest_telegram_user_id = user_id
            test.guest_name = name
            low, high = sorted((test.creator_telegram_user_id, user_id))
            test.pair_key = f"{low}:{high}"
            test.updated_at = datetime.utcnow()
            await session.flush()
        elif test.guest_telegram_user_id != user_id:
            raise HTTPException(status_code=409, detail="test is full")
        return _state(test, user_id)


@router.get("/mine")
async def mine(
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """The caller's latest completed test, with its result."""
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        test = await CompatTestRepository.latest_completed_for(session, user_id)
        if not test:
            raise HTTPException(status_code=404, detail="no completed test")
        result = build_result(test.creator_answers, test.guest_answers, language)
        return {"code": test.code, "result": result.model_dump()}


@router.get("/{code}")
async def state(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)
    async with get_db() as session:
        return _state(await _load(session, code, user_id), user_id)


@router.post("/{code}/answer", dependencies=[Depends(throttle("write"))])
async def answer(
    code: str,
    body: AnswerRequest,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)

    async with get_db() as session:
        # Locked: this is a read-modify-write of the whole answer array, and
        # the client can have several answers in flight.
        test = await _load(session, code, user_id, for_update=True)
        if test.guest_telegram_user_id is None:
            raise HTTPException(status_code=409, detail="partner has not joined yet")
        if test.finished_at is not None:
            raise HTTPException(status_code=409, detail="test is already complete")

        is_creator = user_id == test.creator_telegram_user_id
        answers = list(test.creator_answers if is_creator else test.guest_answers)
        answers[body.index] = body.value
        if is_creator:
            test.creator_answers = answers
        else:
            test.guest_answers = answers

        both_done = (
            _answered(test.creator_answers) == TOTAL_QUESTIONS
            and _answered(test.guest_answers) == TOTAL_QUESTIONS
        )
        just_finished = False
        if both_done and test.finished_at is None:
            test.finished_at = datetime.utcnow()
            just_finished = True
            if test.pair_key:
                await CompatTestRepository.delete_superseded(
                    session, test.pair_key, keep_id=test.id
                )
        test.updated_at = datetime.utcnow()
        await session.flush()
        state = _state(test, user_id)
        # Capture before leaving the block: the notification is sent after the
        # commit, from outside any session. Telling both partners the result
        # is ready before `finished_at` is durable would send them to a 409,
        # and two Telegram round-trips inside the transaction would make the
        # fortieth POST block on the network while holding a pooled connection
        # and a row lock.
        recipients = (
            (test.creator_telegram_user_id, test.guest_telegram_user_id)
            if just_finished else ()
        )

    if recipients:
        await notify_result_ready(recipients, code=state["code"])
    return state


@router.delete("/{code}")
async def delete(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Erase the test and both answer sets. Either participant may do this.

    The answers are about the couple's sex life, money and trust, so neither
    of them should have to complete another eighty questions to get rid of
    them. Either partner acting alone erases the pair's copy: there is one
    shared row, and consent to keep it has to be unanimous.
    """
    user_id, _ = _caller(authorization, x_guest_id)

    async with get_db() as session:
        test = await _load(session, code, user_id)
        await CompatTestRepository.delete(session, test.id)
        logger.info(f"Compat test {test.code} deleted by participant")
        return {"deleted": True}


@router.get("/{code}/result")
async def result(
    code: str,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        test = await _load(session, code, user_id)
        if test.finished_at is None:
            raise HTTPException(status_code=409, detail="both partners must finish")
        return build_result(
            test.creator_answers, test.guest_answers, language
        ).model_dump()
