"""Tell both partners their compatibility result is ready.

The second partner often finishes hours after the first, so without this the
result is computed and never read.
"""

import logging
from collections.abc import Iterable

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Forbidden

from .config import settings
from .i18n import Language, get_text

logger = logging.getLogger(__name__)


def _bot() -> Bot | None:
    """The bot to send with, or None when no token is configured."""
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def _user_language(code: str | None) -> Language:
    try:
        return Language(code)
    except ValueError:
        return Language.RUSSIAN


def _keyboard(language: Language) -> InlineKeyboardMarkup | None:
    """The "open the result" button, or None when WEBAPP_URL is unset.

    `web_app=`, not `url=`: a plain url opens Telegram's in-app browser, where
    `Telegram.WebApp.initData` is empty, so the Mini App falls back to the
    guest path and every /api/compat call 401s in production.
    """
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text("compat.open_button", language),
            web_app=WebAppInfo(url=settings.webapp_url),
        )
    ]])


async def _languages(user_ids: Iterable[int]) -> dict[int, Language]:
    """Each participant's own language, defaulting to Russian."""
    from .payments.database import get_db
    from .payments.repositories import UserRepository

    languages: dict[int, Language] = {}
    try:
        async with get_db() as session:
            for user_id in user_ids:
                user = await UserRepository.get_by_telegram_id(session, user_id)
                languages[user_id] = _user_language(user.language if user else None)
    except Exception as e:
        # A language lookup must never cost the couple their notification.
        logger.warning(f"Compat notify: language lookup failed: {e}")
    return languages


async def notify_result_ready(user_ids: Iterable[int | None], code: str) -> None:
    """Message both participants. One blocked partner must not stop the other.

    Takes ids rather than the ORM row on purpose: the caller sends this
    *after* its transaction has committed, so there is no attached session to
    lazy-load from.
    """
    bot = _bot()
    if bot is None:
        return

    recipients = [user_id for user_id in user_ids if user_id]
    if not recipients:
        return

    languages = await _languages(recipients)

    for user_id in recipients:
        language = languages.get(user_id, Language.RUSSIAN)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=get_text("compat.ready", language),
                reply_markup=_keyboard(language),
            )
        except Forbidden:
            logger.info(f"Compat notify: user {user_id} blocked the bot")
        except Exception as e:
            logger.warning(f"Compat notify failed for {user_id} (test {code}): {e}")
