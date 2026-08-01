"""Library content API for the Mini App.

Mirrors rooms.py: its own router, its own initData handling, the paywall
enforced here rather than in the client. Paid items are never serialized
for an unpaid caller.
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..freemium import FREE_LIBRARY_ITEMS_PER_LIST, free_library_slice
from ..i18n import Language
from ..library import (
    MODULES,
    load_categories,
    load_practices,
    question_of_the_day,
)
from .services import user_has_access
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["library"])


def _language(lang: str) -> Language:
    try:
        return Language(lang)
    except ValueError:
        return Language.RUSSIAN


async def _caller_is_paid(authorization: str | None) -> bool:
    """Whether this caller may see paid Library content."""
    if not settings.enable_payment:
        return True
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return False
    try:
        parsed = validate_init_data(init_data, settings.telegram_bot_token)
    except InitDataError as e:
        logger.warning(f"Library initData rejected: {e}")
        return False
    return await user_has_access(parsed["user"]["id"])


@router.get("")
async def library_index(
    lang: str = "ru",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """The module list for the Library home screen."""
    paid = await _caller_is_paid(authorization)
    return {
        "modules": [
            {
                "id": m.id,
                "title": m.title,
                "emoji": m.emoji,
                "type": m.type,
                "count": m.count,
                "locked": m.paid and not paid,
            }
            for m in MODULES.values()
        ]
    }


@router.get("/{module_id}")
async def library_module(
    module_id: str,
    lang: str = "ru",
    nsfw: int = 0,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """One module's content, already trimmed to what this caller may see."""
    module = MODULES.get(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="unknown module")

    language = _language(lang)
    paid = await _caller_is_paid(authorization)
    locked = module.paid and not paid
    payload: dict[str, Any] = {
        "id": module.id,
        "title": module.title,
        "emoji": module.emoji,
        "type": module.type,
        "locked": locked,
        "free_per_list": FREE_LIBRARY_ITEMS_PER_LIST,
    }

    if module.type == "daily":
        text, day = question_of_the_day(
            date.today().timetuple().tm_yday, language
        )
        payload.update({"question": text, "day": day, "total": module.count})
        return payload

    if module.type == "practice":
        items = load_practices(module_id, language)
        payload.update({
            "items": [i.model_dump() for i in (
                free_library_slice(items) if locked else items
            )],
            "total": len(items),
            "free_count": min(FREE_LIBRARY_ITEMS_PER_LIST, len(items)) if locked else len(items),
        })
        return payload

    categories = [
        c for c in load_categories(module_id, language)
        if not c.nsfw or nsfw == 1
    ]
    payload["categories"] = [
        {
            "id": c.id,
            "title": c.title,
            "nsfw": c.nsfw,
            "items": free_library_slice(c.items) if locked else c.items,
            "total": len(c.items),
        }
        for c in categories
    ]
    payload["total"] = sum(len(c.items) for c in categories)
    payload["free_count"] = sum(
        len(entry["items"]) for entry in payload["categories"]
    )
    return payload
