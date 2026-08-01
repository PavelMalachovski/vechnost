"""The couples compatibility test over HTTP.

Mirrors rooms.py: its own router, its own initData handling, access checked
at creation so the creator's payment covers both partners.

No endpoint here ever serializes a partner's answers. State carries counts;
the result carries zones, verdicts and question numbers.
"""

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..compat import TOTAL_QUESTIONS, build_result, load_spheres, scale_labels
from ..config import settings
from ..i18n import Language
from .database import get_db
from .repositories import CompatTestRepository
from .services import user_has_access
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compat", tags=["compat"])

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class AnswerRequest(BaseModel):
    index: int = Field(ge=0, lt=TOTAL_QUESTIONS)
    value: int = Field(ge=1, le=5)


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def _language(lang: str) -> Language:
    try:
        return Language(lang)
    except ValueError:
        return Language.RUSSIAN


def _caller(
    authorization: str | None, guest_id: str | None
) -> tuple[int, str]:
    """Resolve the caller, exactly as rooms.py does."""
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


async def _load(session, code: str, user_id: int):
    test = await CompatTestRepository.get_by_code(session, code.strip().upper())
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
        "partner_answered": _answered(theirs),
        "total": TOTAL_QUESTIONS,
        "finished": test.finished_at is not None,
        "players": {"creator": test.creator_name, "guest": test.guest_name},
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


@router.post("")
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


@router.post("/{code}/join")
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


@router.post("/{code}/answer")
async def answer(
    code: str,
    body: AnswerRequest,
    lang: str = "ru",
    authorization: str | None = Header(default=None),
    x_guest_id: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)

    async with get_db() as session:
        test = await _load(session, code, user_id)
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
        if both_done and test.finished_at is None:
            test.finished_at = datetime.utcnow()
            if test.pair_key:
                await CompatTestRepository.delete_superseded(
                    session, test.pair_key, keep_id=test.id
                )
        test.updated_at = datetime.utcnow()
        await session.flush()
        return _state(test, user_id)


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
