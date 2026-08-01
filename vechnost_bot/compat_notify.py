"""Tell both partners their compatibility result is ready.

The second partner often finishes hours after the first, so without this the
result is computed and never read.
"""

import logging
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from .config import settings
from .i18n import Language, get_text

logger = logging.getLogger(__name__)


def _bot() -> Optional[Bot]:
    """The bot to send with, or None when no token is configured."""
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def _keyboard() -> Optional[InlineKeyboardMarkup]:
    url = settings.webapp_url
    if not url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text("compat.open_button", Language.RUSSIAN),
            url=url,
        )
    ]])


async def notify_result_ready(test) -> None:
    """Message both participants. One blocked partner must not stop the other."""
    bot = _bot()
    if bot is None:
        return

    text = get_text("compat.ready", Language.RUSSIAN)
    keyboard = _keyboard()

    for user_id in (test.creator_telegram_user_id, test.guest_telegram_user_id):
        if not user_id:
            continue
        try:
            await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
        except Forbidden:
            logger.info(f"Compat notify: user {user_id} blocked the bot")
        except Exception as e:
            logger.warning(f"Compat notify failed for {user_id}: {e}")
