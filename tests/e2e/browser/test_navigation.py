"""Getting around the Mini App the way a phone does: the system Back, the
first seconds after launch, a way back to a game already started, and a
phone that asked for less motion.
"""

from __future__ import annotations

from ..harness import Server
from .app import PROGRESS_JS

POLL = 12_000

# Records, from the first moment the page exists, whether the full-screen
# loader was ever put up: the class change that takes it down still carries
# the `show` it had, so an observer attached after the app's first line of
# script still sees a loader that had already appeared.
WATCH_LOADER = """
document.addEventListener('DOMContentLoaded', () => {
  window.__loaderShown = false;
  const loader = document.getElementById('loader');
  if (loader.classList.contains('show')) window.__loaderShown = true;
  new MutationObserver(records => {
    for (const r of records) {
      if ((r.oldValue || '').split(' ').includes('show') || loader.classList.contains('show')) {
        window.__loaderShown = true;
      }
    }
  }).observe(loader, { attributes: true, attributeFilter: ['class'], attributeOldValue: true });
});
"""


def press_back(phone) -> None:
    """What Telegram does on the Back button or the Android back gesture."""
    phone.page.evaluate("() => window.Telegram.WebApp.BackButton._cb()")


def back_visible(phone) -> bool:
    return bool(phone.page.evaluate("() => window.Telegram.WebApp.BackButton.isVisible"))


def test_back_closes_the_open_overlay_before_the_screen_under_it(server: Server, phones) -> None:
    """D-06: Back under a paywall or the 18+ question used to leave the
    screen - and on the home screen, where Back is hidden, close the app."""
    phone = phones(server.player("Alice"))
    phone.screen("home")
    assert not back_visible(phone)

    phone.page.click("#btnS69")
    phone.page.wait_for_selector("#nsfw.show")
    phone.page.wait_for_function("() => window.Telegram.WebApp.BackButton.isVisible")
    press_back(phone)
    phone.page.wait_for_selector("#nsfw", state="hidden")
    assert phone.page.is_visible("#home.active"), "Back closed the question, not the app"
    phone.page.wait_for_function("() => !window.Telegram.WebApp.BackButton.isVisible")

    # A paywall over a deck: Back closes the paywall, the deck stays.
    phone.page.click("#btnPlay")
    phone.screen("themes")
    phone.page.locator("#themeList .theme-card").first.click()
    phone.screen("levels")
    phone.page.locator("#levelList .level-card").first.click()
    phone.screen("deck")
    for number in range(2, 6):
        phone.page.click("#btnNext")
        phone.page.wait_for_function(
            "t => " + PROGRESS_JS + " === t",
            arg=f"{number} / 5",
        )
    phone.page.click("#btnNext")
    phone.page.wait_for_selector("#paywall.show")
    press_back(phone)
    phone.page.wait_for_selector("#paywall", state="hidden")
    assert phone.page.is_visible("#deck.active")
    phone.shot("deck-after-back")


def test_the_launch_puts_no_loader_over_the_home_screen(server: Server, phones) -> None:
    """D-16: the preload at launch put the full-screen loader over the home
    screen on every launch, for content the home screen does not show."""
    phone = phones(server.player("Alice"), init_script=WATCH_LOADER)
    phone.screen("home")
    phone.page.wait_for_load_state("networkidle")
    assert phone.page.evaluate("() => window.__loaderShown") is False
    phone.page.click("#btnPlay")
    phone.screen("themes")


def test_back_from_the_invite_offers_the_board_already_started(server: Server, phones) -> None:
    """D-19: back from the invite screen, the entry offered nothing, and the
    next board silently left the first one behind."""
    phone = phones(server.player("Alice", paid=True))
    phone.screen("home")
    phone.page.click("#btnS69")
    phone.page.click("#nsfwYes")
    phone.screen("s69")
    phone.page.locator("#s69Suits button").first.click()
    phone.page.click("#btnS69Duo")
    phone.screen("s69Invite")
    press_back(phone)
    phone.screen("s69")
    phone.page.wait_for_selector("#btnS69Resume", state="visible", timeout=POLL)
    phone.shot("resume-offered")


def test_nothing_in_play_is_an_answer_not_an_error(server: Server, phones) -> None:
    """D-37: the board's screen asks /api/steps69/mine on every visit, and
    «Мой результат» asks /api/compat/mine. For someone with nothing in play
    both answered 404, a red line in the console each time. Now it is 200
    and null, and the screens read it as they read the 404."""
    phone = phones(server.player("Alice", paid=True))
    phone.screen("home")
    phone.page.click("#btnS69")
    with phone.page.expect_response(lambda r: "/api/steps69/mine" in r.url):
        phone.page.click("#nsfwYes")
    phone.screen("s69")
    assert phone.page.is_hidden("#btnS69Resume") and phone.page.is_hidden("#btnS69Restart")

    press_back(phone)
    phone.screen("home")
    phone.page.click("#btnCompat")
    phone.screen("compat")
    with phone.page.expect_response(lambda r: "/api/compat/mine" in r.url):
        phone.page.click("#btnCompatMine")
    phone.page.wait_for_selector("#toast.show")
    assert phone.text("#toast") == "У вас пока нет пройденного теста"

    asked = [call for call in phone.api if "/mine" in call.path]
    assert {call.path.split("?")[0] for call in asked} == {"/api/steps69/mine", "/api/compat/mine"}
    assert all(call.status == 200 for call in asked), [str(call) for call in asked]


def test_a_phone_that_asked_for_less_motion_gets_it(server: Server, phones) -> None:
    """D-13: the home screen's fan floated forever and nothing asked the
    phone whether its owner wanted it to."""
    phone = phones(server.player("Alice"))
    phone.screen("home")
    fan = "document.querySelector('.deck-fan i')"
    assert (
        phone.page.evaluate(f"() => getComputedStyle({fan}).animationIterationCount") == "infinite"
    )

    phone.page.emulate_media(reduced_motion="reduce")
    phone.page.reload()
    phone.screen("home")
    style = phone.page.evaluate(
        f"() => {{ const s = getComputedStyle({fan}); "
        "return [s.animationIterationCount, parseFloat(s.animationDuration)]; }"
    )
    assert style[0] == "1" and style[1] < 0.01, style
    # Not floated even once: a float still pending after its delay drew the
    # card differently, and the screen tour's first picture with it.
    pending = phone.page.evaluate(
        "() => [...document.querySelectorAll('.deck-fan i')].map(i => i.getAnimations().length)"
    )
    assert pending == [0, 0, 0, 0], pending
