"""Gift certificates: buy access as a present for another couple.

A dedicated Tribute product (GIFT_PRODUCT_ID) is sold as a gift. When its
payment webhook arrives, the buyer gets a certificate code and a rendered
gift card image instead of personal access; the receiving couple activates
the code with /activate.
"""

import asyncio
import logging
import secrets
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from ..config import settings
from ..i18n import Language, get_text
from ..renderer import get_background_path, render_card
from .repositories import CertificateRepository

logger = logging.getLogger(__name__)

# Unambiguous alphabet (no 0/O, 1/I) — codes are typed by hand.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_gift_code() -> str:
    """Random certificate code: VECH-XXXX-XXXX.

    Short enough to render on the gift card in one line (longer codes get
    hyphen-broken by the renderer, which reads as part of the code).
    """
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"VECH-{body[:4]}-{body[4:]}"


def is_gift_purchase(product_id) -> bool:
    """True if this webhook's product is the configured gift product."""
    if not settings.gift_product_id or product_id is None:
        return False
    return str(product_id) == str(settings.gift_product_id)


async def create_gift_certificate(session: AsyncSession) -> str:
    """Create a certificate with a fresh unique code, return the code."""
    for _ in range(5):
        code = generate_gift_code()
        if not await CertificateRepository.get_by_code(session, code):
            await CertificateRepository.create(session, code=code)
            return code
    raise RuntimeError("could not generate a unique gift code")


def gift_language(language_code: str | None) -> Language:
    return Language.coerce(language_code)


def render_gift_card(code: str, language: Language) -> BytesIO:
    """The gift card image: the code front and center, brand at the bottom."""
    watermark = (
        f"VECHNOST · @{settings.bot_username}" if settings.bot_username else "VECHNOST"
    )
    return render_card(
        code,
        get_background_path("couples", 1, "q"),
        footer=get_text('gift.card_footer', language),
        watermark=watermark,
        single_line=True,
    )


async def deliver_gift_certificate(
    telegram_user_id: int,
    code: str,
    language: Language,
) -> None:
    """Send the buyer their gift card image and activation instructions."""
    bot = Bot(token=settings.telegram_bot_token)
    caption = get_text('gift.delivered', language).format(
        code=code, bot=settings.bot_username or ""
    )
    try:
        image = await asyncio.to_thread(render_gift_card, code, language)
        await bot.send_photo(
            chat_id=telegram_user_id,
            photo=image.getvalue(),
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Gift card image delivery failed, sending text: {e}")
        await bot.send_message(
            chat_id=telegram_user_id, text=caption, parse_mode="HTML"
        )


async def get_gift_purchase_url() -> str | None:
    """Payment link for the gift product, or the configured fallback page."""
    if settings.gift_product_id:
        from .services import get_products_for_purchase

        for product in await get_products_for_purchase():
            if str(product.id) == str(settings.gift_product_id):
                link = product.t_link or product.web_link
                if link:
                    return link
    return settings.gift_payment_url
