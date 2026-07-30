"""Daily card push: one card a day, sent to everyone who hasn't opted out.

The card of the day is deterministic per calendar date and shared by all
users; each user receives it rendered in their own language. NSFW themes
are never pushed.
"""

import logging
from datetime import date

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from .config import settings
from .i18n import Language, get_text
from .logic import localized_game_data
from .models import ContentType, Theme
from .renderer import get_background_path, render_card

logger = logging.getLogger(__name__)

# Themes safe for unsolicited pushes (no NSFW).
ELIGIBLE_THEMES = [Theme.ACQUAINTANCE, Theme.FOR_COUPLES, Theme.PROVOCATION]

# Knuth's multiplicative hash constant: spreads consecutive days across
# the pool so the sequence doesn't walk through one deck in order.
_HASH = 2654435761


def _deck_specs() -> list[tuple[Theme, int | None, int]]:
    """(theme, level, deck size) for every pushable deck, in stable order."""
    specs: list[tuple[Theme, int | None, int]] = []
    for theme in ELIGIBLE_THEMES:
        levels = localized_game_data.get_available_levels(theme, Language.RUSSIAN)
        for level in levels or [None]:
            items = localized_game_data.get_content(
                theme, level, ContentType.QUESTIONS, Language.RUSSIAN
            )
            if items:
                specs.append((theme, level, len(items)))
    return specs


def pick_daily_card(day: date) -> tuple[Theme, int | None, int]:
    """Deterministic (theme, level, card index) for a calendar date."""
    specs = _deck_specs()
    pool_size = sum(size for _, _, size in specs)
    position = (day.toordinal() * _HASH) % pool_size
    for theme, level, size in specs:
        if position < size:
            return theme, level, position
        position -= size
    raise RuntimeError("empty daily card pool")  # unreachable with valid data


def _user_language(code: str | None) -> Language:
    try:
        return Language(code)
    except ValueError:
        return Language.RUSSIAN


def _daily_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            get_text('daily.play_button', language),
            callback_data="start_game"
        )],
        [InlineKeyboardButton(
            get_text('daily.unsubscribe_button', language),
            callback_data="daily_off"
        )],
    ])


def render_daily_card(day: date, language: Language):
    """Rendered card image + caption for the given date and language."""
    theme, level, idx = pick_daily_card(day)
    items = localized_game_data.get_content(
        theme, level, ContentType.QUESTIONS, language
    )
    text = items[idx]

    bg_path = get_background_path(theme.value_short(), level or 0, "q")
    watermark = (
        f"VECHNOST · @{settings.bot_username}" if settings.bot_username else "VECHNOST"
    )
    image = render_card(
        text,
        bg_path,
        footer=get_text('daily.card_footer', language),
        watermark=watermark,
    )
    caption = f"{get_text('daily.title', language)}\n{get_text('daily.subtitle', language)}"
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

    today = date.today()
    # Render once per language, reuse the bytes for every user.
    rendered: dict[Language, tuple[bytes, str]] = {}
    sent = 0

    for user in recipients:
        language = _user_language(user.language)
        if language not in rendered:
            image, caption = render_daily_card(today, language)
            rendered[language] = (image.getvalue(), caption)
        image_bytes, caption = rendered[language]

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
