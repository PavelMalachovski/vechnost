"""Tell whoever sent an invite that the partner has come.

The inviter usually shares the link and closes the app: nothing on their
screen is polling any more, and a partner who opens the link an hour later
would find a game nobody is playing. So the moment the guest takes the seat
(`partners.seat_taken`), the bot tells the creator, with a button straight
back into that game.

Sent by the web process after the join has committed, the way
`compat_notify` sends a finished test: a fresh `Bot`, closed afterwards,
never raising. A creator who has no chat with the bot - a Mini App user who
never allowed messages - simply is not told. Nothing here logs the game's
code: it is a seat in somebody's game.
"""

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Forbidden

from ..config import settings
from ..i18n import Language, get_text
from .partners import Seated

logger = logging.getLogger(__name__)

# What the message says, by the screen the game opens on.
TEXTS = {
    "coop": "partner.joined_room",
    "compat": "partner.joined_compat",
    "steps69": "partner.joined_steps69",
}


def _bot() -> Bot | None:
    """The bot to send with, or None when no token is configured."""
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def _keyboard(seated: Seated, language: Language) -> InlineKeyboardMarkup | None:
    """The button back into this very game, or None without WEBAPP_URL.

    `web_app=`, not `url=`: a plain url opens Telegram's in-app browser,
    where there is no initData and the app cannot tell the creator from a
    stranger. The app re-opens its own game from `?screen=&code=`.
    """
    url = settings.webapp_join_url(seated.screen, seated.code)
    if not url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text("partner.open_button", language), web_app=WebAppInfo(url=url)
        )
    ]])


async def _language(telegram_user_id: int) -> Language:
    from .database import get_db
    from .repositories import UserRepository

    try:
        async with get_db() as session:
            user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
            return Language.coerce(user.language if user else None)
    except Exception as e:
        logger.warning(f"Partner notify: language lookup failed: {e}")
        return Language.RUSSIAN


def message_for(seated: Seated, language: Language = Language.RUSSIAN) -> str:
    """The words, with the guest's own first name or «Партнёр»."""
    name = (seated.guest_name or "").strip() or get_text("partner.someone", language)
    return get_text(TEXTS[seated.screen], language, name=name)


async def notify_partner_joined(seated: Seated) -> None:
    """Message the creator that their partner has taken the seat. Never raises."""
    bot = _bot()
    if bot is None or seated.screen not in TEXTS:
        return
    language = await _language(seated.creator_id)
    try:
        async with bot:
            try:
                await bot.send_message(
                    chat_id=seated.creator_id,
                    text=message_for(seated, language),
                    reply_markup=_keyboard(seated, language),
                )
            except Forbidden:
                logger.info("Partner notify: the creator has no chat with the bot")
            except Exception as e:
                logger.warning(f"Partner notify failed: {e}")
    except Exception as e:
        # initialize()/shutdown() can themselves fail on a dead network.
        logger.warning(f"Partner notify failed: {e}")
