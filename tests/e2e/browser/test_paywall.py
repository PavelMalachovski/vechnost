"""The paywall and the 18+ gates, on the phones that meet them.

The API suites prove who may see what. These prove what a person is shown
at each door a payment opens: that the paywall says what the payment buys,
that paying brings them back to where they stopped rather than to card 1 or
to the same paywall, that a payment by either partner opens a free room for
both, and that nobody is seated at an 18+ table before saying they are 18.
"""

from __future__ import annotations

import re

from ...wording import plain
from ..harness import Server, code_from_invite

POLL = 12_000  # the app polls every ~2.5 s and backs off on errors
YOUR_TURN = "✨ Твой ход"
PAY_ITEMS = [
    "все 4 колоды целиком, все уровни",
    "тест совместимости для пар",
    "интерактивную игру «69 ступеней» 18+",
    "мастер-класс по нюдсам",
    "идеи для свиданий и практики для пар",
]


def press_back(phone) -> None:
    """Telegram's Back: inside Telegram the page's own «←» is hidden (audit
    D-25), and the header's Back does what it did."""
    phone.page.evaluate("() => window.Telegram.WebApp.BackButton._cb()")


def progress_is(phone, text: str, timeout: float = POLL) -> None:
    phone.page.wait_for_function(
        "t => document.getElementById('progressNum').innerText.trim() === t",
        arg=text,
        timeout=timeout,
    )


def open_first_deck(phone) -> None:
    phone.screen("home")
    phone.page.click("#btnPlay")
    phone.screen("themes")
    phone.page.locator("#themeList .theme-card").first.click()
    phone.screen("levels")
    phone.page.locator("#levelList .level-card").first.click()
    phone.screen("deck")


def play_the_free_cards(phone) -> str:
    """Turn the five free cards; returns the lead the paywall opens with."""
    progress_is(phone, "1 / 5")
    for number in range(2, 6):
        phone.page.click("#btnNext")
        progress_is(phone, f"{number} / 5")
    phone.page.click("#btnNext")
    phone.page.wait_for_selector("#paywall.show")
    return phone.text("#paywallLead")


def test_the_end_of_the_free_cards_says_what_a_payment_opens(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    open_first_deck(phone)
    lead = play_the_free_cards(phone)
    phone.shot("paywall")

    assert phone.text("#paywallTitle") == "Бесплатные карты закончились"
    assert re.fullmatch(r"Вы прошли 5 бесплатных карт из \d+\.", lead), lead
    assert [
        plain(item) for item in phone.page.locator("#paywallList li").all_inner_texts()
    ] == PAY_ITEMS
    assert "доступ навсегда" in phone.text(".pay-promise")
    assert phone.text("#paywallBuy").startswith("💳 Открыть всё")
    assert phone.page.is_visible("#paywallRefresh")


def test_paying_carries_on_at_the_next_card_not_at_card_one(server: Server, phones) -> None:
    alice = server.player("Alice")
    phone = phones(alice)
    open_first_deck(phone)
    play_the_free_cards(phone)

    # Asked before the money arrived: the paywall stays, and says why.
    phone.page.click("#paywallRefresh")
    phone.page.wait_for_function(
        "() => document.getElementById('toast').innerText.replace(/\\u00a0/g, ' ').includes('Оплата ещё не пришла')"
    )
    assert phone.page.is_visible("#paywall")

    # «Открыть всё», the payment page, the webhook, and back into view.
    phone.page.click("#paywallBuy")
    server.grant(alice)
    phone.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    phone.page.wait_for_selector("#paywall", state="hidden", timeout=POLL)
    phone.page.wait_for_function(
        "() => /^6 \\/ \\d+$/.test(document.getElementById('progressNum').innerText.trim())",
        timeout=POLL,
    )
    total = int(phone.text("#progressNum").split("/")[1])
    assert total > 5, "the whole deck, not the free five"
    phone.shot("after-payment")

    # Reopened later, the deck is where it was, and whole.
    press_back(phone)
    phone.screen("levels")
    phone.page.locator("#levelList .level-card").first.click()
    phone.screen("deck")
    progress_is(phone, f"6 / {total}")


def test_the_compatibility_test_without_access_opens_the_paywall(server: Server, phones) -> None:
    phone = phones(server.player("Alice"))
    phone.screen("home")
    phone.page.click("#btnCompat")
    phone.screen("compat")
    phone.page.click("#btnCompatCreate")
    phone.page.wait_for_selector("#paywall.show")
    phone.shot("compat-paywall")
    assert phone.text("#paywallTitle") == "Полный доступ"
    assert phone.text("#paywallLead") == "Тест совместимости входит в полный доступ."
    assert [
        plain(item) for item in phone.page.locator("#paywallList li").all_inner_texts()
    ] == PAY_ITEMS


def test_either_partner_paying_opens_a_free_room_for_both(server: Server, phones) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")

    a = phones(alice)
    a.screen("home")
    a.page.click("#btnCoop")
    a.screen("coop")
    a.page.click("#btnCoopCreate")
    a.screen("themes")
    a.page.locator("#themeList .theme-card").first.click()
    a.screen("levels")
    a.page.locator("#levelList button").first.click()
    a.screen("invite")
    invite = a.text("#inviteCode")

    b = phones(bob, start_param=f"duo_{code_from_invite(invite)}")
    b.screen("deck")
    a.screen("deck", timeout=POLL)

    # Five free cards, taken in turns.
    for turn in range(5):
        mover = a if turn % 2 == 0 else b
        mover.page.wait_for_function(
            "t => document.querySelector('#turnChipText')?.innerText.trim() === t",
            arg=YOUR_TURN,
            timeout=POLL,
        )
        mover.page.click("#btnNext")
        if turn < 4:
            for phone in (a, b):
                progress_is(phone, f"{turn + 2} / 5")

    # The last free card is an offer to both, not «Колода пройдена!».
    for phone in (a, b):
        phone.page.wait_for_selector("#paywall.show", timeout=POLL)
        lead = phone.text("#paywallLead")
        assert re.fullmatch(
            r"Это были 5 бесплатных карт из \d+\. Откройте всю колоду для вас обоих: "
            r"платит один, играете вдвоём\.",
            lead,
        ), lead
        assert not phone.page.is_visible("#done")
    a.shot("room-offer")

    # The guest pays; the next poll on each phone deals the rest in.
    server.grant(bob)
    for phone in (a, b):
        phone.page.wait_for_selector("#paywall", state="hidden", timeout=POLL)
        phone.page.wait_for_function(
            "() => /^6 \\/ \\d+$/.test(document.getElementById('progressNum').innerText.trim())",
            timeout=POLL,
        )
    assert a.text("#stage .card.top .q-text") == b.text("#stage .card.top .q-text")
    a.shot("room-opened")
    b.shot("room-opened")


def test_the_board_asks_for_18_before_its_first_screen(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True))
    phone.screen("home")
    phone.page.click("#btnS69")
    phone.page.wait_for_selector("#nsfw.show")
    assert "«69 ступеней»" in phone.text("#nsfwText")
    phone.shot("s69-gate")
    phone.page.click("#nsfwNo")
    phone.screen("home")

    phone.page.click("#btnS69")
    phone.page.click("#nsfwYes")
    phone.screen("s69")

    # Asked once: the answer is remembered.
    press_back(phone)
    phone.screen("home")
    phone.page.click("#btnS69")
    phone.screen("s69")
    assert not phone.page.is_visible("#nsfw")


def test_an_invite_to_the_18_plus_deck_seats_nobody_before_the_answer(
    server: Server, phones
) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    room = alice.ok(
        "POST", "/api/rooms?lang=ru", {"theme": "Sex", "level": None, "type": "questions"}
    )
    code = room["code"]

    def seated() -> bool:
        return bool(alice.ok("GET", f"/api/rooms/{code}?lang=ru")["started"])

    no = phones(bob, start_param=f"duo_{code}")
    no.page.wait_for_selector("#nsfw.show")
    assert not seated(), "the seat waits for the answer"
    no.page.click("#nsfwNo")
    no.screen("home")
    assert not seated(), "a partner who says no is never seated"

    yes = phones(bob, start_param=f"duo_{code}")
    yes.page.wait_for_selector("#nsfw.show")
    yes.page.click("#nsfwYes")
    yes.screen("deck")
    assert seated()
    yes.shot("seated")
