"""Tests for the daily self-reflection push."""

import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


@pytest.mark.parametrize("language", list(Language))
def test_renders_in_every_language(language):
    image, caption = render_daily_card(date(2026, 3, 3), language)
    assert image.getvalue()
    assert caption.strip()


async def test_blocked_user_is_opted_out():
    from telegram.error import Forbidden

    user = MagicMock(telegram_user_id=42, language="ru")
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=Forbidden("blocked"))

    with patch("vechnost_bot.payments.repositories.UserRepository") as repo:
        repo.get_daily_card_recipients = AsyncMock(return_value=[user])
        repo.set_daily_card_opt_out = AsyncMock()
        with patch("vechnost_bot.daily_card.get_db"):
            sent = await send_daily_cards(bot)

    assert sent == 0
