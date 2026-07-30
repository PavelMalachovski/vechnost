"""Tests for gift certificates."""

import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

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
    assert gift_language("en") == Language.ENGLISH
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
        async def create(session, code):
            created.append(code)

    with patch("vechnost_bot.payments.gifts.CertificateRepository", FakeRepo):
        code = await create_gift_certificate(MagicMock())

    assert created == [code]
    assert FakeRepo.calls == 2  # first candidate collided, second was fresh


def test_render_gift_card_produces_image():
    image = render_gift_card("VECH-ABCD-EFGH", Language.RUSSIAN)
    assert len(image.getvalue()) > 10_000
