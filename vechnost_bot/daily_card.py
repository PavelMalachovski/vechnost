"""Daily self-reflection push: one prompt a day for everyone who hasn't opted out.

The prompt is deterministic per calendar date and shared by all users; each
user receives it rendered in their own language.
"""

import logging
from datetime import UTC, date, datetime
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import Forbidden

from .config import settings
from .i18n import Language, get_text
from .library import REFLECTION_TOTAL, question_of_the_day
from .renderer import render_card

logger = logging.getLogger(__name__)

# The daily prompt belongs to no deck, so it rides the Library card: the
# brand face with the V/Λ letters and the VECHNOST wordmark, and no suit.
_BACKGROUND = str(
    Path(__file__).parent.parent / "assets" / "backgrounds" / "library.png"
)


def _user_language(code: str | None) -> Language:
    return Language.coerce(code)


def _daily_keyboard(language: Language) -> InlineKeyboardMarkup:
    """One way in, and one way out.

    The push used to carry «Играть» and «Библиотека», which were two names
    for the same app opened at two screens — a choice made before the reader
    had seen either. It is one button now, and the app's own home screen is
    where the choosing belongs. Opting out stays: it is the only thing here
    that is not the app.

    Without WEBAPP_URL there is no app to open, so the card falls back to the
    bot's own deck rather than showing a dead row.
    """
    rows = []
    if settings.webapp_url:
        rows.append([InlineKeyboardButton(
            get_text('daily.open_app_button', language),
            web_app=WebAppInfo(url=settings.webapp_url)
        )])
    else:
        rows.append([InlineKeyboardButton(
            get_text('daily.open_app_button', language),
            callback_data="start_game"
        )])
    rows.append([InlineKeyboardButton(
        get_text('daily.unsubscribe_button', language),
        callback_data="daily_off"
    )])
    return InlineKeyboardMarkup(rows)


def render_daily_card(day: date, language: Language):
    """Rendered prompt image + caption for the given date and language."""
    text, number = question_of_the_day(day.timetuple().tm_yday, language)
    watermark = (
        f"VECHNOST · @{settings.bot_username}" if settings.bot_username else "VECHNOST"
    )
    image = render_card(
        text,
        _BACKGROUND,
        footer=get_text('daily.card_footer', language, day=number,
                        total=REFLECTION_TOTAL),
        watermark=watermark,
    )
    caption = (
        f"{get_text('daily.title', language)}\n"
        f"{get_text('daily.subtitle', language, day=number, total=REFLECTION_TOTAL)}"
    )
    return image, caption


async def send_daily_cards(bot: Bot) -> int:
    """Send today's card to every recipient. Returns how many were sent."""
    from .payments.database import get_db
    from .payments.repositories import UserRepository

    async with get_db() as session:
        recipients = await UserRepository.get_daily_card_recipients(session)

    if not recipients:
        logger.info("Daily card: no recipients")
        return 0

    # The job fires on a UTC clock, so the calendar date is read from the
    # same clock: `date.today()` is server-local and rolls the prompt at the
    # wrong moment on any non-UTC host.
    today = datetime.now(UTC).date()
    # Render once per language, reuse the bytes for every user.
    rendered: dict[Language, tuple[bytes, str]] = {}
    render_failed: set[Language] = set()
    sent = 0

    for user in recipients:
        language = _user_language(user.language)
        if language in render_failed:
            continue
        try:
            # Inside the per-user try on purpose: a render failure used to
            # kill the whole job before the first send.
            if language not in rendered:
                image, caption = render_daily_card(today, language)
                rendered[language] = (image.getvalue(), caption)
            image_bytes, caption = rendered[language]
        except Exception as e:
            logger.error(f"Daily card: render failed for {language}: {e}")
            render_failed.add(language)
            continue

        try:
            await bot.send_photo(
                chat_id=user.telegram_user_id,
                photo=image_bytes,
                caption=caption,
                reply_markup=_daily_keyboard(language),
            )
            sent += 1
        except Forbidden:
            # User blocked the bot — stop pushing to them.
            async with get_db() as session:
                await UserRepository.set_daily_card_opt_out(
                    session, user.telegram_user_id, True
                )
            logger.info(f"Daily card: user {user.telegram_user_id} blocked the bot, opted out")
        except Exception as e:
            logger.warning(f"Daily card: failed for {user.telegram_user_id}: {e}")

    logger.info(f"Daily card: sent to {sent}/{len(recipients)} recipients")
    return sent


async def daily_card_job(context) -> None:
    """PTB JobQueue entry point."""
    await send_daily_cards(context.bot)
