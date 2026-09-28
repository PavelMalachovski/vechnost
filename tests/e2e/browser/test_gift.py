"""A gift, from the home screen and from the paywall.

The certificate arrives as a message from the bot, so the sheet asks
Telegram for permission to write first whenever the bot cannot write to the
buyer yet: a gift paid for and never delivered is the worst way this goes.
Someone the bot can already write to goes straight to the payment page.

The server offers the gift from GIFT_PRODUCT_ID or GIFT_PAYMENT_URL, which
the shared live server does not set; the phones here add the two fields to
`/api/questions` themselves (`WITH_A_GIFT`). The server side of the offer is
held by `tests/test_access_product.py`.
"""

from __future__ import annotations

import json

from ..harness import Server

GIFT = "https://t.me/tribute/app?startapp=pGIFT"
PRICE = "7,90 €"

# Runs before the app's own script: `/api/questions` answers with a gift.
WITH_A_GIFT = """(() => {
  const real = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const res = await real(input, init);
    const url = String((input && input.url) || input);
    if (!url.includes('/api/questions')) return res;
    const json = await res.clone().json();
    json.access = Object.assign({}, json.access, __GIFT__);
    return new Response(JSON.stringify(json), { status: res.status, headers: res.headers });
  };
})();""".replace("__GIFT__", json.dumps({"gift_url": GIFT, "gift_price": PRICE}))


# The space above the home column's first child and below its last, inside
# the padding: equal while #home centres a column that fits.
GAPS = """() => {
  const home = document.getElementById('home');
  const box = home.getBoundingClientRect(), cs = getComputedStyle(home);
  const kids = [...home.children].filter(el => el.getClientRects().length);
  return [
    kids[0].getBoundingClientRect().top - box.top - parseFloat(cs.paddingTop),
    box.bottom - parseFloat(cs.paddingBottom) - kids[kids.length - 1].getBoundingClientRect().bottom,
  ];
}"""


def assert_centred(phone) -> None:
    """A hidden gift button at the end of #home once took the centring with
    it, and the whole home screen sank to the bottom of a tall phone."""
    phone.page.set_viewport_size({"width": 430, "height": 932})
    top, bottom = phone.page.evaluate(GAPS)
    assert top > 0 and abs(top - bottom) <= 2, (top, bottom)


def calls(phone) -> list[list[str]]:
    return phone.page.evaluate("() => window.__tg.calls")


def links(phone) -> list[str]:
    return phone.page.evaluate("() => window.__tg.links")


def test_a_buyer_the_bot_cannot_reach_is_asked_before_paying(server: Server, phones) -> None:
    bob = server.player("Bob", allows_write=False)
    phone = phones(bob, init_script=WITH_A_GIFT)
    phone.screen("home")
    phone.page.click("#btnGift")
    phone.page.wait_for_selector("#giftSheet.show")
    assert phone.text("#giftPrice") == f"Сертификат: {PRICE}"
    assert phone.page.is_visible("#giftNote")
    phone.shot("gift")

    phone.page.click("#giftBuy")
    phone.page.wait_for_selector("#giftSheet", state="hidden")
    assert ["requestWriteAccess"] in calls(phone)
    assert links(phone) == [GIFT]


def test_a_buyer_the_bot_can_write_to_goes_straight_to_the_page(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)  # allows_write_to_pm: true
    phone = phones(alice, init_script=WITH_A_GIFT)
    phone.screen("home")
    phone.page.wait_for_selector("#btnGift")
    assert_centred(phone)
    phone.page.click("#btnGift")
    phone.page.wait_for_selector("#giftSheet.show")
    assert not phone.page.is_visible("#giftNote")
    phone.page.click("#giftBuy")
    phone.page.wait_for_selector("#giftSheet", state="hidden")
    assert ["requestWriteAccess"] not in calls(phone)
    assert links(phone) == [GIFT]


def test_the_paywall_sells_a_gift_too(server: Server, phones) -> None:
    carol = server.player("Carol")  # unpaid: the compatibility test is a paywall
    phone = phones(carol, init_script=WITH_A_GIFT)
    phone.screen("home")
    phone.page.click("#btnCompat")
    phone.screen("compat")
    phone.page.click("#btnCompatCreate")
    phone.page.wait_for_selector("#paywall.show")
    phone.page.click("#paywallGift")
    phone.page.wait_for_selector("#giftSheet.show")
    assert not phone.page.is_visible("#paywall")
    phone.page.click("#giftClose")
    phone.page.wait_for_selector("#giftSheet", state="hidden")
    assert links(phone) == []


def test_no_gift_on_offer_no_gift_button(server: Server, phones) -> None:
    phone = phones(server.player("Dan"))
    phone.screen("home")
    phone.page.wait_for_selector("#homeModules .home-mod")
    assert phone.page.locator("#btnGift").count() == 0
    assert_centred(phone)
