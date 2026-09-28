"""Tests for gift certificates."""

import os
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from telegram import Chat, Message, MessageEntity
from telegram import User as TelegramUser

from vechnost_bot.config import settings
from vechnost_bot.i18n import Language
from vechnost_bot.payments.gifts import (
    create_gift_certificate,
    generate_gift_code,
    gift_language,
    is_gift_purchase,
    render_gift_card,
)


def test_gift_code_format():
    for _ in range(20):
        code = generate_gift_code()
        assert re.fullmatch(r"VECH-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
        # no ambiguous characters
        assert not set(code) & {"0", "O", "1", "I"}


def test_gift_codes_are_unique_enough():
    codes = {generate_gift_code() for _ in range(200)}
    assert len(codes) == 200


def test_is_gift_purchase_disabled_without_setting():
    with patch.object(settings, "gift_product_id", None):
        assert not is_gift_purchase(123)


def test_is_gift_purchase_matches_configured_product():
    with patch.object(settings, "gift_product_id", "123"):
        assert is_gift_purchase(123)
        assert is_gift_purchase("123")
        assert not is_gift_purchase(456)
        assert not is_gift_purchase(None)


def test_gift_language_fallback():
    """`en` is a pre-single-language code carried over from old certificates;
    every code now coerces to Russian, the only language left."""
    assert gift_language("en") == Language.RUSSIAN
    assert gift_language("de") == Language.RUSSIAN
    assert gift_language(None) == Language.RUSSIAN


@pytest.mark.asyncio
async def test_create_gift_certificate_retries_on_collision():
    existing = MagicMock()
    created = []

    class FakeRepo:
        calls = 0

        @staticmethod
        async def get_by_code(session, code):
            FakeRepo.calls += 1
            return existing if FakeRepo.calls == 1 else None

        @staticmethod
        async def create(session, code, purchase_id=None):
            created.append(code)

    with patch("vechnost_bot.payments.gifts.CertificateRepository", FakeRepo):
        code = await create_gift_certificate(MagicMock())

    assert created == [code]
    assert FakeRepo.calls == 2  # first candidate collided, second was fresh


def test_render_gift_card_produces_image():
    image = render_gift_card("VECH-ABCD-EFGH", Language.RUSSIAN)
    assert len(image.getvalue()) > 10_000


# ---------------------------------------------------------------------------
# The card's caption, and the question its link opens on
# ---------------------------------------------------------------------------


def test_the_caption_carries_the_link_to_forward():
    from vechnost_bot.payments.gifts import delivered_caption

    with patch.object(settings, "bot_username", "vechnost_bot"):
        caption = delivered_caption("VECH-ABCD-EFGH", Language.RUSSIAN)
    assert 'href="https://t.me/vechnost_bot?start=activate_VECH-ABCD-EFGH"' in caption
    assert "/activate VECH-ABCD-EFGH" in caption

    # Without the bot's handle there is no link to give, only the command.
    with patch.object(settings, "bot_username", None):
        caption = delivered_caption("VECH-ABCD-EFGH", Language.RUSSIAN)
    assert "href" not in caption and "{" not in caption
    assert "/activate VECH-ABCD-EFGH" in caption


def _question(text: str, code: str | None) -> Message:
    """The bot's own question, as Telegram hands it back under a button."""
    entities = []
    if code:
        # Telegram counts in UTF-16 units: the 🎁 before the code is two.
        offset = len(text[: text.index(code)].encode("utf-16-le")) // 2
        entities = [MessageEntity(MessageEntity.CODE, offset, len(code))]
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=5, type=Chat.PRIVATE),
        text=text,
        entities=entities,
    )


async def test_opening_the_link_asks_and_spends_nothing():
    from vechnost_bot import handlers

    message = AsyncMock()
    with patch("vechnost_bot.payments.services.user_has_access", AsyncMock(return_value=False)):
        await handlers.ask_to_activate(message, 5, "vech-abcd-efgh")
    text = message.reply_text.await_args.args[0]
    keyboard = message.reply_text.await_args.kwargs["reply_markup"]
    assert "VECH-ABCD-EFGH" in text
    data = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert data == [handlers.ACTIVATE, handlers.NOT_NOW]
    assert all("VECH" not in d for d in data)  # the code never rides in a button


async def test_someone_with_access_is_told_to_give_it_away():
    from vechnost_bot import handlers
    from vechnost_bot.i18n import get_text

    message = AsyncMock()
    with patch("vechnost_bot.payments.services.user_has_access", AsyncMock(return_value=True)):
        await handlers.ask_to_activate(message, 5, "VECH-ABCD-EFGH")
    assert get_text("gift.confirm_has_access") in message.reply_text.await_args.args[0]


@pytest.mark.parametrize(
    "result, key, has_button",
    [
        ({"status": "success"}, "certificate.activated", True),
        ({"status": "error", "code": 409, "yours": True}, "certificate.already_yours", True),
        ({"status": "error", "code": 409, "yours": False}, "certificate.already_used", False),
        ({"status": "error", "code": 404}, "certificate.not_found", False),
        ({"status": "error", "code": 410}, "certificate.revoked", False),
        ({"status": "error", "code": 500}, "certificate.error", False),
    ],
)
async def test_the_button_activates_the_code_its_question_carries(result, key, has_button):
    from vechnost_bot import handlers
    from vechnost_bot.i18n import get_text

    query = AsyncMock()
    query.data = handlers.ACTIVATE
    query.from_user = TelegramUser(id=5, first_name="Bob", is_bot=False)
    query.message = _question("🎁 Подарочный сертификат VECH-ABCD-EFGH ...", "VECH-ABCD-EFGH")
    update = MagicMock(callback_query=query)
    activate = AsyncMock(return_value=result)
    with (
        patch("vechnost_bot.payments.services.activate_certificate", activate),
        patch.object(settings, "webapp_url", "https://example.com/app/"),
    ):
        await handlers.activate_callback(update, None)
    assert activate.await_args.kwargs["code"] == "VECH-ABCD-EFGH"
    assert activate.await_args.kwargs["telegram_user_id"] == 5
    text = query.edit_message_text.await_args.args[0]
    markup = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert text == get_text(key)
    assert (markup is not None) is has_button


async def test_not_now_spends_nothing():
    from vechnost_bot import handlers
    from vechnost_bot.i18n import get_text

    query = AsyncMock()
    query.data = handlers.NOT_NOW
    query.message = _question("VECH-ABCD-EFGH", "VECH-ABCD-EFGH")
    activate = AsyncMock()
    with patch("vechnost_bot.payments.services.activate_certificate", activate):
        await handlers.activate_callback(MagicMock(callback_query=query), None)
    activate.assert_not_awaited()
    assert query.edit_message_text.await_args.args[0] == get_text("gift.later")


def test_the_code_is_read_back_from_the_code_the_question_set():
    from vechnost_bot.handlers import _code_in

    # The <code> entity, as Telegram reports it - whatever the code looks like.
    assert _code_in(_question("Сертификат OLD-VOUCHER-7 готов", "OLD-VOUCHER-7")) == "OLD-VOUCHER-7"
    # No entity (an old client, a copy): the shape of a code.
    assert _code_in(_question("код vech-abcd-efgh", None)) == "VECH-ABCD-EFGH"
    assert _code_in(_question("ничего", None)) is None
    assert _code_in(object()) is None  # a message Telegram no longer shows
