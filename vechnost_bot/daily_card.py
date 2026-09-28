"""Daily self-reflection push: one prompt a day for everyone who hasn't opted out.

The prompt is deterministic per calendar date and shared by all users; each
user receives it rendered in their own language.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from .config import settings
from .i18n import Language, get_text
from .jobs import Run
from .library import REFLECTION_TOTAL, question_of_the_day
from .renderer import render_card

logger = logging.getLogger(__name__)

# Its row in `job_runs` and its Sentry monitor.
JOB_NAME = "daily_card"

# The daily prompt belongs to no deck, so it rides the Library card: the
# brand face with the V/Λ letters and the VECHNOST wordmark, and no suit.
_BACKGROUND = str(Path(__file__).parent.parent / "assets" / "backgrounds" / "library.png")


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
        rows.append(
            [
                InlineKeyboardButton(
                    get_text("daily.open_app_button", language),
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    get_text("daily.open_app_button", language), callback_data="start_game"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                get_text("daily.unsubscribe_button", language), callback_data="daily_off"
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def render_daily_card(day: date, language: Language) -> tuple[BytesIO, str]:
    """Rendered prompt image + caption for the given date and language."""
    text, number = question_of_the_day(day.timetuple().tm_yday, language)
    watermark = f"VECHNOST · @{settings.bot_username}" if settings.bot_username else "VECHNOST"
    image = render_card(
        text,
        _BACKGROUND,
        footer=get_text("daily.card_footer", language, day=number, total=REFLECTION_TOTAL),
        watermark=watermark,
    )
    caption = (
        f"{get_text('daily.title', language)}\n"
        f"{get_text('daily.subtitle', language, day=number, total=REFLECTION_TOTAL)}"
    )
    return image, caption


# The list is read a page at a time as the run goes: somebody who opts out
# mid-run is not sent to, and memory does not grow with the audience.
RECIPIENTS_PER_PAGE = 500


async def send_daily_cards(bot: Bot, run: Run | None = None) -> int:
    """Send the day's card to every recipient. Returns how many were sent.

    `run` is the day's claimed run (`jobs.py`): recipients are taken in id
    order after its cursor, and the cursor moves after each one, so a run
    cut short by a restart is resumed after the last person reached rather
    than started over or dropped. Without one - a test, a hand-run - the
    list is sent from the top with nothing recorded.

    Each send goes through `broadcast.deliver`, which is the one delivery
    loop the bot has: a pause between sends, Telegram's own `retry_after`
    honoured and the send retried, and a user who blocked the bot opted
    out. This function used to have its own loop with none of that, so
    once flood control tripped - a few thousand recipients is enough -
    every remaining send in the window failed unretried and the job ended
    with «sent 900/3000» as if that were fine.
    """
    from . import broadcast
    from .payments.database import get_db
    from .payments.repositories import UserRepository

    # The run's own date, not today's: a run resumed after midnight still
    # sends the card of the day it belongs to. It is a UTC date either way,
    # like the clock the job fires on.
    run = run or Run.detached_for(JOB_NAME, datetime.now(UTC).date())
    day = run.day
    # Render once per language, reuse the bytes for every user.
    rendered: dict[Language, tuple[bytes, str]] = {}
    render_failed: set[Language] = set()
    # Telegram returns a file_id for the first upload of an image; every
    # later recipient gets the id instead of the same hundred kilobytes.
    file_ids: dict[Language, str] = {}
    sent = 0
    after = run.cursor

    while True:
        async with get_db() as session:
            page = [
                (user.telegram_user_id, user.language)
                for user in await UserRepository.get_daily_card_recipients(
                    session, after=after, limit=RECIPIENTS_PER_PAGE
                )
            ]
        if not page:
            break

        for user_id, code in page:
            run.check()
            after = user_id
            language = _user_language(code)
            if language in render_failed:
                await run.advance(user_id, broadcast.FAILED)
                continue
            try:
                # Inside the per-user try on purpose: a render failure used
                # to kill the whole job before the first send. In a thread:
                # this runs on the bot's loop, which handles every tap
                # meanwhile.
                if language not in rendered:
                    image, caption = await asyncio.to_thread(render_daily_card, day, language)
                    rendered[language] = (image.getvalue(), caption)
                image_bytes, caption = rendered[language]
            except Exception as e:
                logger.error(f"Daily card: render failed for {language}: {e}")
                render_failed.add(language)
                await run.advance(user_id, broadcast.FAILED)
                continue

            async def send(
                chat_id: int,
                _language: Language = language,
                _bytes: bytes = image_bytes,
                _caption: str = caption,
            ) -> Any:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=file_ids.get(_language, _bytes),
                    caption=_caption,
                    reply_markup=_daily_keyboard(_language),
                )
                if _language not in file_ids:
                    try:
                        file_ids[_language] = message.photo[-1].file_id
                    except Exception:
                        pass  # an unusual reply shape costs a re-upload, nothing more
                return message

            status = await broadcast.deliver(send, user_id)
            if status == broadcast.SENT:
                sent += 1
            await run.advance(user_id, status)
            await asyncio.sleep(broadcast.SECONDS_BETWEEN_SENDS)

    logger.info(
        f"Daily card for {day}: sent to {run.sent} "
        f"({run.blocked} blocked the bot, {run.failed} failed)"
        + (" - resumed after a restart" if run.resumed else "")
    )
    return sent


async def run_daily_card(bot: Bot, run: Run) -> None:
    """The scheduler's entry point (`jobs.DailyJob.run`)."""
    await send_daily_cards(bot, run)
