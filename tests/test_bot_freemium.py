"""Tests for the bot-side freemium card gate."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.callback_handlers import (
    _card_is_locked_for,
    _card_watermark,
    _send_card_paywall,
)
from vechnost_bot.config import settings
from vechnost_bot.freemium import FREE_CARDS_PER_DECK
from vechnost_bot.i18n import Language

pytestmark = pytest.mark.asyncio


def make_query():
    query = MagicMock()
    query.from_user.id = 42
    query.message.reply_text = AsyncMock()
    return query


def test_watermark_with_username():
    with patch.object(settings, "bot_username", "tvoya_vechnost_bot"):
        assert _card_watermark() == "VECHNOST · @tvoya_vechnost_bot"


def test_watermark_without_username():
    with patch.object(settings, "bot_username", None):
        assert _card_watermark() == "VECHNOST"


async def test_everything_unlocked_when_payments_disabled():
    with patch.object(settings, "enable_payment", False):
        assert not await _card_is_locked_for(make_query(), 100)


async def test_free_cards_open_without_payment():
    with patch.object(settings, "enable_payment", True):
        for i in range(FREE_CARDS_PER_DECK):
            assert not await _card_is_locked_for(make_query(), i)


async def test_paid_card_locked_without_access():
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.services.user_has_access",
            AsyncMock(return_value=False),
        ),
    ):
        assert await _card_is_locked_for(make_query(), FREE_CARDS_PER_DECK)


async def test_paid_card_open_with_access():
    with (
        patch.object(settings, "enable_payment", True),
        patch(
            "vechnost_bot.payments.services.user_has_access",
            AsyncMock(return_value=True),
        ),
    ):
        assert not await _card_is_locked_for(make_query(), FREE_CARDS_PER_DECK)


async def test_paywall_message_includes_price():
    query = make_query()
    with (
        patch(
            "vechnost_bot.payments.services.get_price_label",
            AsyncMock(return_value="4,99 €"),
        ),
        patch(
            "vechnost_bot.payments.middleware.get_payment_keyboard",
            AsyncMock(return_value=None),
        ),
    ):
        await _send_card_paywall(query, Language.RUSSIAN)

    query.message.reply_text.assert_awaited_once()
    text = query.message.reply_text.call_args.args[0]
    assert "🔒" in text
    assert str(FREE_CARDS_PER_DECK) in text
    assert "4,99 €" in text


async def test_paywall_message_without_price():
    query = make_query()
    with (
        patch(
            "vechnost_bot.payments.services.get_price_label",
            AsyncMock(return_value=None),
        ),
        patch(
            "vechnost_bot.payments.middleware.get_payment_keyboard",
            AsyncMock(return_value=None),
        ),
    ):
        await _send_card_paywall(query, Language.ENGLISH)

    text = query.message.reply_text.call_args.args[0]
    assert "🔒" in text
    assert "{price}" not in text
