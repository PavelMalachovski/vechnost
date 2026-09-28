"""Getting around the Mini App the way a phone does: the system Back, the
first seconds after launch, a way back to a game already started, and a
phone that asked for less motion.
"""

from __future__ import annotations

from ..harness import Server

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


# Every scroll position the board's map reports, from the page's first moment.
WATCH_MAP = """
window.__mapScrolls = [];
document.addEventListener('scroll', e => {
  if (e.target && e.target.id === 's69Map') window.__mapScrolls.push(e.target.scrollTop);
}, true);
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
            "t => document.getElementById('progressNum').innerText.trim() === t",
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


def test_the_board_follows_the_piece_without_travel_when_asked(server: Server, phones) -> None:
    """D-13, the map: it keeps the piece in frame with scrollIntoView, and a
    smooth scroll asked for by script is not the CSS scroll-behavior that the
    reduced-motion block turns off. The map travelled for half a second on a
    phone that asked for less motion."""
    alice, bob = server.player("Alice", paid=True), server.player("Bob")
    game = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})
    code = game["code"]
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    # Far enough down that the capped map has to scroll to show the piece.
    for _ in range(200):
        state = alice.ok("GET", f"/api/steps69/{code}")
        if state["you"]["position"] >= 30:
            break
        (alice if state["your_turn"] else bob).ok("POST", f"/api/steps69/{code}/roll")

    board = phones(
        alice,
        start_param=f"s69_{code}",
        reduced_motion=True,
        viewport={"width": 320, "height": 568},
        init_script=WATCH_MAP,
    )
    board.page.wait_for_selector("#nsfw.show, #s69Board.active")
    if board.page.is_visible("#nsfwYes"):
        board.page.click("#nsfwYes")
    board.screen("s69Board", timeout=POLL)
    board.page.wait_for_selector("#s69Map .s69-cell.here .s69-piece")
    board.page.wait_for_timeout(1_000)
    seen = board.page.evaluate("() => window.__mapScrolls")
    # A map that travels reports its scroll a frame at a time; one that
    # jumps, once for each place it jumps to.
    assert seen, "the piece should be out of the first rows' frame"
    assert len(set(seen)) <= 2, f"the map travelled through {sorted(set(seen))}"


# Whether the viewer's own piece sits whole inside the map's frame.
PIECE_IN_FRAME = """() => {
  const map = document.getElementById('s69Map');
  const m = map.getBoundingClientRect();
  const c = map.querySelector('.s69-cell.here').getBoundingClientRect();
  return c.top >= m.top - 1 && c.bottom <= m.bottom + 1;
}"""


def test_the_board_keeps_the_piece_in_frame_when_the_map_changes_size(
    server: Server, phones
) -> None:
    """The map scrolled to the piece only when the state moved it, so a
    phone turned or a window resized left the piece out of frame until the
    next poll - and the visual check caught the map on either side of that
    poll behind the finale."""
    alice, bob = server.player("Alice", paid=True), server.player("Bob")
    game = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})
    code = game["code"]
    bob.ok("POST", f"/api/steps69/{code}/join", {})
    for _ in range(200):
        state = alice.ok("GET", f"/api/steps69/{code}")
        if state["you"]["position"] >= 48:
            break
        (alice if state["your_turn"] else bob).ok("POST", f"/api/steps69/{code}/roll")

    board = phones(
        alice,
        start_param=f"s69_{code}",
        reduced_motion=True,
        viewport={"width": 430, "height": 932},
    )
    board.page.wait_for_selector("#nsfw.show, #s69Board.active")
    if board.page.is_visible("#nsfwYes"):
        board.page.click("#nsfwYes")
    board.screen("s69Board", timeout=POLL)
    board.page.wait_for_selector("#s69Map .s69-cell.here .s69-piece")
    assert board.page.evaluate(PIECE_IN_FRAME)
    # Well inside one poll: the frame follows the map's size, not the state.
    board.page.set_viewport_size({"width": 320, "height": 568})
    board.page.wait_for_timeout(150)
    assert board.page.evaluate(PIECE_IN_FRAME), "the piece left the frame on a resize"
