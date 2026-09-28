"""Which product the paywalls sell (backend audit B-10).

`/admin/sync-products` copies Tribute's whole catalogue: the access itself,
the gift certificate and, once there is one, the referral discount. The
Mini App's buy button took the cheapest product with a link and showed the
cheapest price, and the bot put a button under every product - so as soon
as the gift or the discount was synced, an ordinary visitor was offered it.
`ACCESS_PRODUCT_ID` names the product outright; without it the gift and
the discount are never the access.
"""

import os
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.payments.middleware import get_payment_keyboard
from vechnost_bot.payments.repositories import ProductRepository, UserRepository
from vechnost_bot.payments.web import app

ACCESS_LINK = "https://t.me/tribute/app?startapp=pACCESS"
REFERRAL_LINK = "https://t.me/tribute/app?startapp=pREFERRAL"
GIFT_LINK = "https://t.me/tribute/app?startapp=pGIFT"
FALLBACK = "https://tribute.invalid/pay"

# Cheapest first is exactly the order the old choice read them in: the gift,
# then the discount, then the access everyone was meant to buy.
CATALOGUE = (
    (3, "Подарочный сертификат", 790, GIFT_LINK),
    (2, "Доступ со скидкой", 891, REFERRAL_LINK),
    (1, "Доступ навсегда", 990, ACCESS_LINK),
)


@pytest.fixture
def shop(tmp_path) -> Iterator[TestClient]:
    """Payments on, the whole catalogue synced, the gift and discount configured.

    One client for the whole test, and the database is set up on its event
    loop: the engine is bound to the loop that opened it.
    """
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'shop.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
        patch.object(settings, "enable_payment", True),
        patch.object(settings, "tribute_payment_url", FALLBACK),
        patch.object(settings, "gift_product_id", "3"),
        patch.object(settings, "gift_payment_url", None),
        patch.object(settings, "referral_payment_url", REFERRAL_LINK),
        patch.object(settings, "access_product_id", None),
        TestClient(app) as client,
    ):

        async def sync() -> None:
            async with database.get_db() as session:
                for product_id, name, amount, link in CATALOGUE:
                    await ProductRepository.upsert(
                        session,
                        product_id=product_id,
                        type="digital",
                        name=name,
                        amount=amount,
                        currency="eur",
                        t_link=link,
                    )

        client.portal.call(sync)
        yield client


def paywall(client: TestClient, user_id: int | None = None) -> dict:
    """The `access` block the Mini App gets, for a visitor or a signed-in user."""
    if user_id is None:
        return client.get("/api/questions").json()["access"]
    with (
        patch(
            "vechnost_bot.payments.web.validate_init_data",
            return_value={"user": {"id": user_id, "first_name": "X"}},
        ),
        patch("vechnost_bot.payments.web.user_has_access", AsyncMock(return_value=False)),
    ):
        return client.get("/api/questions", headers={"Authorization": "tma x"}).json()["access"]


def bot_urls(client: TestClient, user_id: int | None = None) -> list[str]:
    """The URL buttons under the bot's paywall, after checking the other one."""

    async def keyboard():
        return await get_payment_keyboard("ru", telegram_user_id=user_id)

    rows = client.portal.call(keyboard).inline_keyboard
    buttons = [button for row in rows for button in row]
    assert [b.callback_data for b in buttons if b.callback_data] == ["check_payment"]
    return [b.url for b in buttons if b.url]


def invite(client: TestClient, inviter: int, invitee: int) -> None:
    async def go() -> None:
        async with database.get_db() as session:
            await UserRepository.create_or_update(session, telegram_user_id=inviter)
            await UserRepository.create_or_update(session, telegram_user_id=invitee)
            code = await UserRepository.ensure_referral_code(session, inviter)
            assert code
            assert await UserRepository.record_referral(session, invitee, code)

    client.portal.call(go)


def test_the_configured_access_product_is_sold_even_when_others_are_cheaper(shop):
    with patch.object(settings, "access_product_id", "1"):
        access = paywall(shop)
    assert access["payment_url"] == ACCESS_LINK
    assert access["price"] == "9,90 €"


def test_without_the_setting_neither_the_gift_nor_the_discount_is_the_access(shop):
    access = paywall(shop)
    assert access["payment_url"] == ACCESS_LINK, "the gift is cheaper and must not be sold instead"
    assert access["price"] == "9,90 €"


def test_a_configured_product_that_is_not_synced_is_never_replaced_by_a_guess(shop):
    with patch.object(settings, "access_product_id", "99"):
        access = paywall(shop)
    assert access["payment_url"] == FALLBACK
    assert access["price"] is None, "no price is better than another product's price"


def test_an_invited_user_still_gets_the_discounted_page(shop):
    invite(shop, inviter=501, invitee=502)
    with patch.object(settings, "access_product_id", "1"):
        invited, ordinary = paywall(shop, 502), paywall(shop, 501)
    assert invited["payment_url"] == REFERRAL_LINK
    assert invited["discount_percent"] == settings.referral_discount_percent
    assert ordinary["payment_url"] == ACCESS_LINK
    assert "discount_percent" not in ordinary


def test_the_bot_offers_one_purchase_button_not_the_catalogue(shop):
    with patch.object(settings, "access_product_id", "1"):
        assert bot_urls(shop, 601) == [ACCESS_LINK]
    assert bot_urls(shop, 601) == [ACCESS_LINK], "and without the setting too"


def test_the_bot_sends_an_invited_user_to_the_discounted_page(shop):
    invite(shop, inviter=701, invitee=702)
    assert bot_urls(shop, 702) == [REFERRAL_LINK]
    assert bot_urls(shop, 701) == [ACCESS_LINK]


def test_with_nothing_synced_both_paywalls_link_the_payment_page(shop):
    async def empty() -> None:
        from sqlalchemy import delete

        from vechnost_bot.payments.models import Product

        async with database.get_db() as session:
            await session.execute(delete(Product))

    shop.portal.call(empty)
    assert bot_urls(shop) == [FALLBACK]
    assert paywall(shop)["payment_url"] == FALLBACK


# ---------------------------------------------------------------------------
# The gift, in the Mini App
# ---------------------------------------------------------------------------


def test_the_gift_is_offered_to_everyone_at_its_own_price(shop):
    """The gift rides outside the unpaid branch: a couple who has paid is who
    gives it most. Its price is the gift product's, never the access's."""
    visitor = paywall(shop)
    assert (visitor["gift_url"], visitor["gift_price"]) == (GIFT_LINK, "7,90 €")
    assert visitor["payment_url"] != GIFT_LINK

    with (
        patch(
            "vechnost_bot.payments.web.validate_init_data",
            return_value={"user": {"id": 7, "first_name": "X"}},
        ),
        patch("vechnost_bot.payments.web.user_has_access", AsyncMock(return_value=True)),
    ):
        paid = shop.get("/api/questions", headers={"Authorization": "tma x"}).json()["access"]
    assert paid["paid"] is True
    assert (paid["gift_url"], paid["gift_price"]) == (GIFT_LINK, "7,90 €")


def test_a_gift_page_without_a_synced_product_has_no_price(shop):
    with (
        patch.object(settings, "gift_product_id", "404"),
        patch.object(settings, "gift_payment_url", FALLBACK + "/gift"),
    ):
        access = paywall(shop)
    assert access["gift_url"] == FALLBACK + "/gift"
    assert "gift_price" not in access


def test_no_gift_configured_no_gift_offered(shop):
    with (
        patch.object(settings, "gift_product_id", None),
        patch.object(settings, "gift_payment_url", None),
    ):
        access = paywall(shop)
    assert "gift_url" not in access and "gift_price" not in access
