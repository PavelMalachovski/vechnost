"""Tests for the daily card push."""

import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.daily_card import (
    ELIGIBLE_THEMES,
    _eligible_cards,
    _excluded_texts,
    pick_daily_card,
    render_daily_card,
)
from vechnost_bot.i18n import Language
from vechnost_bot.logic import localized_game_data
from vechnost_bot.models import ContentType, Theme


def test_pool_excludes_nsfw_themes():
    themes = {theme for theme, _, _ in _eligible_cards()}
    assert Theme.SEX not in themes
    assert themes == set(ELIGIBLE_THEMES)


def test_pool_is_curated():
    # 210 safe-theme questions minus the curated exclude list
    excluded = _excluded_texts()
    assert len(excluded) > 0
    assert len(_eligible_cards()) == 210 - len(excluded)


def test_excluded_texts_never_picked():
    excluded = _excluded_texts()
    assert "Как ты относишься к “легким” наркотикам?" in excluded
    for theme, level, idx in _eligible_cards():
        text = localized_game_data.get_content(
            theme, level, ContentType.QUESTIONS, Language.RUSSIAN
        )[idx]
        assert text.strip() not in excluded


def test_exclude_list_matches_real_questions():
    # Every excluded text must still exist in the source YAML; a mismatch
    # means the question was edited and the exclusion silently expired.
    all_texts = set()
    for theme in ELIGIBLE_THEMES:
        levels = localized_game_data.get_available_levels(theme, Language.RUSSIAN)
        for level in levels or [None]:
            items = localized_game_data.get_content(
                theme, level, ContentType.QUESTIONS, Language.RUSSIAN
            )
            all_texts.update(t.strip() for t in items or [])
    stale = _excluded_texts() - all_texts
    assert not stale, f"exclusions no longer match any question: {stale}"


def test_pick_is_deterministic():
    day = date(2026, 7, 30)
    assert pick_daily_card(day) == pick_daily_card(day)


def test_pick_varies_between_days():
    picks = {pick_daily_card(date(2026, 7, 1) + timedelta(days=i)) for i in range(14)}
    assert len(picks) > 7  # the hash spreads days across decks


def test_pick_index_within_deck():
    for i in range(30):
        theme, level, idx = pick_daily_card(date(2026, 1, 1) + timedelta(days=i))
        items = localized_game_data.get_content(
            theme, level, ContentType.QUESTIONS, Language.RUSSIAN
        )
        assert 0 <= idx < len(items)


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
