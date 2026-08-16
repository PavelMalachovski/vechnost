"""Tests for the daily self-reflection push."""

import asyncio
import os
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.daily_card import render_daily_card, send_daily_cards
from vechnost_bot.i18n import Language
from vechnost_bot.library import question_of_the_day


def test_caption_carries_the_day_number():
    day = date(2026, 2, 16)          # day 47 of the year
    assert day.timetuple().tm_yday == 47
    _, number = question_of_the_day(47, Language.RUSSIAN)
    assert number == 47
    _, caption = render_daily_card(day, Language.RUSSIAN)
    assert "47" in caption
    assert "365" in caption


def test_same_day_renders_the_same_card():
    day = date(2026, 5, 5)
    first, _ = render_daily_card(day, Language.RUSSIAN)
    second, _ = render_daily_card(day, Language.RUSSIAN)
    assert first.getvalue() == second.getvalue()


def test_first_and_last_day_of_the_year_render():
    for day in (date(2026, 1, 1), date(2026, 12, 31)):
        image, caption = render_daily_card(day, Language.RUSSIAN)
        assert image.getvalue()
        assert caption.strip()


def test_leap_day_renders_without_raising():
    image, _ = render_daily_card(date(2028, 12, 31), Language.RUSSIAN)   # day 366
    assert image.getvalue()


def test_renders_in_russian():
    image, caption = render_daily_card(date(2026, 3, 3), Language.RUSSIAN)
    assert image.getvalue()
    assert caption.strip()


# `send_daily_cards` imports `get_db` and `UserRepository` inside the function,
# so both are patched where they are defined, not on `daily_card`.
#
# These two run the coroutine themselves instead of relying on pytest-asyncio:
# the repo's session-scoped `event_loop` fixture in tests/conftest.py makes every
# `async def` test error out with ScopeMismatch, and that fixture is out of scope
# here. Driving the loop directly keeps the send path genuinely covered.


def _run_send(bot, recipients, repo_extra=None):
    """Run send_daily_cards against a mocked DB and repository."""
    with patch("vechnost_bot.payments.repositories.UserRepository") as repo:
        repo.get_daily_card_recipients = AsyncMock(return_value=recipients)
        repo.set_daily_card_opt_out = AsyncMock()
        if repo_extra is not None:
            repo_extra.append(repo)
        with patch("vechnost_bot.payments.database.get_db"):
            return asyncio.run(send_daily_cards(bot))


def test_healthy_recipient_gets_the_card():
    user = MagicMock(telegram_user_id=42, language="ru")
    bot = MagicMock()
    bot.send_photo = AsyncMock()

    sent = _run_send(bot, [user])

    assert sent == 1
    bot.send_photo.assert_awaited_once()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["chat_id"] == 42

    image, caption = render_daily_card(date.today(), Language.RUSSIAN)
    assert kwargs["photo"] == image.getvalue()
    assert kwargs["caption"] == caption

    labels = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "daily_off" in labels


def test_library_button_appears_only_when_the_mini_app_is_configured():
    from vechnost_bot.config import settings
    from vechnost_bot.daily_card import _daily_keyboard

    original = settings.webapp_url
    try:
        settings.webapp_url = None
        rows = _daily_keyboard(Language.RUSSIAN).inline_keyboard
        assert all(b.web_app is None for row in rows for b in row)

        settings.webapp_url = "https://example.com/app"
        rows = _daily_keyboard(Language.RUSSIAN).inline_keyboard
        library = [b for row in rows for b in row if b.web_app]
        assert len(library) == 1
        assert library[0].web_app.url.endswith("screen=library")
    finally:
        settings.webapp_url = original


def test_blocked_user_is_opted_out():
    from telegram.error import Forbidden

    user = MagicMock(telegram_user_id=42, language="ru")
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=Forbidden("blocked"))
    captured = []

    sent = _run_send(bot, [user], repo_extra=captured)

    assert sent == 0
    captured[0].set_daily_card_opt_out.assert_awaited_once()


def test_daily_card_uses_the_library_face():
    """The daily prompt is a Library item, so it must ride the Library card,
    not the blank framed default the deck falls back to."""
    from vechnost_bot import daily_card

    assert Path(daily_card._BACKGROUND).name == "library.png"
    assert Path(daily_card._BACKGROUND).exists()
