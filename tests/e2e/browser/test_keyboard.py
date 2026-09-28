"""The Mini App from a keyboard - Telegram Desktop, a browser - and to a
screen reader (audit D-14). tests/test_webapp_a11y.py holds the markup;
this presses the keys, on both phones.
"""

from __future__ import annotations

from ..harness import Server
from .app import PROGRESS_JS


def focused(phone) -> str:
    return phone.page.evaluate("() => document.activeElement && document.activeElement.id")


def open_deck(phone) -> None:
    phone.page.click("#btnPlay")
    phone.screen("themes")
    phone.page.locator("#themeList .theme-card").first.click()
    phone.screen("levels")
    phone.page.locator("#levelList .level-card").first.click()
    phone.screen("deck")


def wait_for_card(phone, number: int) -> None:
    phone.page.wait_for_function(
        "n => " + PROGRESS_JS + ".startsWith(n + ' /')",
        arg=number,
    )


def test_the_arrows_turn_the_cards(server: Server, phones) -> None:
    """A deck in Telegram Desktop could only be turned with the mouse."""
    phone = phones(server.player("Alice"))
    phone.screen("home")
    open_deck(phone)
    wait_for_card(phone, 1)
    assert phone.page.get_attribute("#btnNext", "aria-label") == "Следующая карта"
    assert phone.page.get_attribute("#btnPrev", "aria-label") == "Предыдущая карта"

    phone.page.keyboard.press("ArrowRight")
    wait_for_card(phone, 2)
    phone.page.keyboard.press("ArrowRight")
    wait_for_card(phone, 3)
    phone.page.keyboard.press("ArrowLeft")
    wait_for_card(phone, 2)


def test_a_layer_takes_the_focus_keeps_tab_inside_and_gives_it_back(server: Server, phones) -> None:
    """The 18+ question over the home screen: the focus used to stay on the
    button behind it, Tab walked out under the layer, and nothing but a
    tap closed it."""
    phone = phones(server.player("Alice"))
    phone.screen("home")
    phone.page.focus("#btnS69")
    phone.page.keyboard.press("Enter")
    phone.page.wait_for_selector("#nsfw.show")
    assert focused(phone) == "nsfw", "the layer takes the focus, not its «yes»"

    walked = []
    for _ in range(4):
        phone.page.keyboard.press("Tab")
        walked.append(focused(phone))
    assert walked == ["nsfwYes", "nsfwNo", "nsfwYes", "nsfwNo"]
    phone.page.keyboard.press("Shift+Tab")
    assert focused(phone) == "nsfwYes"

    phone.page.keyboard.press("Escape")
    phone.page.wait_for_selector("#nsfw", state="hidden")
    assert phone.page.is_visible("#home.active"), "Escape closed the question, not the screen"
    assert focused(phone) == "btnS69", "the focus came back where the layer was opened"
