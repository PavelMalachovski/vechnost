"""Tests for the daily card push."""

import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.daily_card import (
    ELIGIBLE_THEMES,
    _deck_specs,
    pick_daily_card,
    render_daily_card,
)
from vechnost_bot.i18n import Language
from vechnost_bot.models import Theme


def test_pool_excludes_nsfw_themes():
    themes = {theme for theme, _, _ in _deck_specs()}
    assert Theme.SEX not in themes
    assert themes == set(ELIGIBLE_THEMES)


def test_pool_covers_all_safe_decks():
    # Acquaintance 3 levels + For Couples 3 levels + Provocation flat deck
    assert len(_deck_specs()) == 7
    total = sum(size for _, _, size in _deck_specs())
    assert total == 210  # 6 level decks * 30 + provocation 30


def test_pick_is_deterministic():
    day = date(2026, 7, 30)
    assert pick_daily_card(day) == pick_daily_card(day)


def test_pick_varies_between_days():
    picks = {pick_daily_card(date(2026, 7, 1) + timedelta(days=i)) for i in range(14)}
    assert len(picks) > 7  # the hash spreads days across decks


def test_pick_index_within_deck():
    for i in range(30):
        theme, level, idx = pick_daily_card(date(2026, 1, 1) + timedelta(days=i))
        specs = {(t, l): size for t, l, size in _deck_specs()}
        assert 0 <= idx < specs[(theme, level)]


def test_render_daily_card_produces_image_and_caption():
    image, caption = render_daily_card(date(2026, 7, 30), Language.RUSSIAN)
    assert len(image.getvalue()) > 10_000
    assert "Карта дня" in caption


@pytest.mark.asyncio
async def test_send_daily_cards_marks_blocked_users():
    from telegram.error import Forbidden

    from vechnost_bot.daily_card import send_daily_cards

    user_ok = MagicMock(telegram_user_id=1, language="ru")
    user_blocked = MagicMock(telegram_user_id=2, language="en")

    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=[None, Forbidden("blocked")])

    opt_out_calls = []

    class FakeRepo:
        @staticmethod
        async def get_daily_card_recipients(session):
            return [user_ok, user_blocked]

        @staticmethod
        async def set_daily_card_opt_out(session, telegram_user_id, opt_out):
            opt_out_calls.append((telegram_user_id, opt_out))

    class FakeDb:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *args):
            return False

    with (
        patch("vechnost_bot.payments.database.get_db", lambda: FakeDb()),
        patch("vechnost_bot.payments.repositories.UserRepository", FakeRepo),
    ):
        sent = await send_daily_cards(bot)

    assert sent == 1
    assert opt_out_calls == [(2, True)]
