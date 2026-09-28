"""Tell a buyer, in the chat, that their access is open.

A purchase happens on Tribute's page, outside the app, and nothing on that
page says what was bought or where to go next. The Mini App notices when it
is looked at again, but a buyer who paid from a link in the chat, or closed
the app to pay, came back to silence. So the moment Tribute confirms the
purchase, the bot says so: open for good, a button straight into the app, and
the one fact a couple most often asks about - the partner does not pay again.

Sent by the web process after the webhook has been answered (see
`web.tribute_webhook`), the way `compat_notify` sends a finished test: a fresh
`Bot`, closed afterwards, never raising. Never for a gift - the buyer gets a
certificate to hand on, not access - nor for a duplicate delivery, a refund,
a cancellation or an event nobody knows; `apply_webhook_event` reports which
it was, and the endpoint only calls this for a grant of the buyer's own.
"""

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Forbidden

from ..config import settings
from ..i18n import Language, get_text

logger = logging.getLogger(__name__)


def _bot() -> Bot | None:
    """The bot to send with, or None when no token is configured."""
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def _keyboard(language: Language) -> InlineKeyboardMarkup | None:
    """The button into the app, or None when WEBAPP_URL is unset.

    `web_app=`, not `url=`: a plain url opens Telegram's in-app browser,
    where `Telegram.WebApp.initData` is empty and the app cannot tell the
    buyer from a stranger - it would show them the paywall they just paid.
    """
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("grant.open_button", language),
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )


async def _language(telegram_user_id: int) -> Language:
    """The buyer's own language, Russian when it cannot be read."""
    from .database import get_db
    from .repositories import UserRepository

    try:
        async with get_db() as session:
            user = await UserRepository.get_by_telegram_id(session, telegram_user_id)
            return Language.coerce(user.language if user else None)
    except Exception as e:
        # A language lookup must never cost the buyer their message.
        logger.warning(f"Grant notify: language lookup failed: {e}")
        return Language.RUSSIAN


async def notify_access_granted(telegram_user_id: int, lifetime: bool = True) -> None:
    """Message the buyer that everything is open. Never raises.

    `lifetime` picks the words: «навсегда» only for a purchase that is.
    """
    bot = _bot()
    if bot is None or not telegram_user_id:
        return

    language = await _language(telegram_user_id)

    # `async with` closes the Bot's HTTP pool afterwards: this runs in the
    # long-lived web process, once per purchase.
    try:
        async with bot:
            try:
                await bot.send_message(
                    chat_id=telegram_user_id,
                    text=get_text(
                        "grant.message" if lifetime else "grant.message_subscription", language
                    ),
                    reply_markup=_keyboard(language),
                )
            except Forbidden:
                # Paid through a link without ever opening a chat with the
                # bot, or blocked it since. The access is theirs either way.
                logger.info(f"Grant notify: user {telegram_user_id} has no chat with the bot")
            except Exception as e:
                logger.warning(f"Grant notify failed for {telegram_user_id}: {e}")
    except Exception as e:
        # initialize()/shutdown() can themselves fail on a dead network;
        # the buyer just doesn't get the message this time.
        logger.warning(f"Grant notify failed for {telegram_user_id}: {e}")
