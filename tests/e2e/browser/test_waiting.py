"""Waiting and loading, as the phone shows them (audit D-38).

- What is on its way holds its place: the home screen's last two rows and
  the Practices list stand as shimmering skeletons until /api/library
  answers, so the home screen does not jump when they arrive and the list
  is not an empty screen under a spinner.
- Waiting for the partner is a live state: a dot breathes in front of
  «Ждём партнёра…», and leaves the room's chip once the partner is in.
- A button whose answer is on its way says so and takes no second tap:
  «Прошлый результат» sat still for as long as /api/compat/mine took.
- What destroys something two people share looks dangerous: the test's
  «Удалить» and the board's «Начать заново».
"""

from __future__ import annotations

from ..harness import Server, code_from_invite

POLL = 12_000


def hold(path: str) -> str:
    """An init script that holds every request to `path` until the test
    lets it go, from before the app's own script runs."""
    return """
window.__held = [];
window.__hold = true;
const realFetch = window.fetch.bind(window);
window.fetch = (url, init) => {
  if (window.__hold && String(url).includes(PATH)) {
    return new Promise(go => window.__held.push(() => go(realFetch(url, init))));
  }
  return realFetch(url, init);
};
window.__release = () => { window.__hold = false; window.__held.splice(0).forEach(go => go()); };
""".replace("PATH", repr(path))


# Where an element stands on its screen, which slides 12px as it comes in.
TOP_ON_SCREEN = """(sel) => {
    const el = document.querySelector(sel);
    return el.getBoundingClientRect().top - el.closest('.screen').getBoundingClientRect().top;
}"""

DOT = """(sel) => {
    const dot = getComputedStyle(document.querySelector(sel), '::before');
    return dot.content !== 'none' && dot.width === '7px';
}"""


def test_nothing_jumps_while_the_modules_load(server: Server, phones) -> None:
    phone = phones(server.player("Alice"), init_script=hold("/api/library"))
    phone.screen("home")
    assert phone.page.locator("#homeModules .skeleton").count() == 2
    assert phone.page.get_attribute("#homeModules", "aria-busy") == "true"
    before = phone.page.evaluate(TOP_ON_SCREEN, "#btnPlay")
    phone.shot("home-loading")

    phone.page.evaluate("window.__release()")
    phone.page.wait_for_selector("#homeModules button")
    assert phone.page.locator("#homeModules .skeleton").count() == 0
    assert phone.page.get_attribute("#homeModules", "aria-busy") is None
    after = phone.page.evaluate(TOP_ON_SCREEN, "#btnPlay")
    assert abs(after - before) <= 1, f"«Играть» moved {after - before:+.1f}px when the rows came"

    # The Practices list, the first time: skeleton rows, not an empty screen.
    phone.page.evaluate("window.__hold = true")
    phone.tap("#btnPractices")
    phone.screen("library")
    assert phone.page.locator("#libraryList .skeleton").count() == 5
    assert not phone.page.is_visible("#loader"), "the full-screen loader over an empty list"
    phone.shot("library-loading")
    phone.page.evaluate("window.__release()")
    phone.page.wait_for_selector("#libraryList [data-module]")
    assert phone.page.locator("#libraryList .skeleton").count() == 0
    assert phone.page.get_attribute("#libraryList", "aria-busy") is None


def test_waiting_for_the_partner_breathes(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    phone = phones(alice)
    phone.screen("home")
    phone.tap("#btnCoop")
    phone.screen("coop")
    assert not phone.page.evaluate(DOT, "#coop .coop-box > p"), "a door is not a wait"
    phone.tap("#btnCoopCreate")
    phone.screen("themes")
    phone.page.locator("#themeList .theme-card").first.tap()
    phone.screen("levels")
    phone.page.locator("#levelList .level-card").first.tap()
    phone.screen("invite")
    phone.page.wait_for_function("() => document.getElementById('inviteWaiting').textContent")
    assert phone.page.evaluate(DOT, "#inviteWaiting"), "«Ждём партнёра…» without its dot"

    room = code_from_invite(phone.text("#inviteCode"))
    server.player("Bob").ok("POST", f"/api/rooms/{room}/join")
    phone.screen("deck", timeout=POLL)
    phone.page.wait_for_function(
        "() => !document.getElementById('turnChipText').classList.contains('waiting')",
        timeout=POLL,
    )
    assert not phone.page.evaluate(DOT, "#turnChipText"), "the chip still waits"


def test_a_button_waiting_for_its_answer_says_so(server: Server, phones) -> None:
    phone = phones(server.player("Alice", paid=True), init_script=hold("/api/compat/mine"))
    phone.screen("home")
    phone.tap("#btnCompat")
    phone.screen("compat")
    phone.tap("#btnCompatMine")
    assert phone.page.get_attribute("#btnCompatMine", "aria-busy") == "true"
    phone.shot("past-result-busy")
    phone.page.evaluate("document.getElementById('btnCompatMine').click()")
    assert phone.page.evaluate("window.__held.length") == 1, "a second tap asked again"

    phone.page.evaluate("window.__release()")
    phone.page.wait_for_selector("#toast.show")
    assert phone.page.get_attribute("#btnCompatMine", "aria-busy") is None
    assert "busy" not in (phone.page.get_attribute("#btnCompatMine", "class") or "")


def test_what_destroys_a_shared_thing_looks_dangerous(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})
    phone = phones(alice)
    phone.screen("home")
    phone.tap("#btnS69")
    phone.tap("#nsfwYes")
    phone.screen("s69")
    phone.page.wait_for_selector("#btnS69Restart", state="visible")
    danger = phone.page.evaluate(
        "() => getComputedStyle(document.documentElement).getPropertyValue('--c-red-300').trim()"
    )
    restart = phone.page.evaluate(
        "() => getComputedStyle(document.getElementById('btnS69Restart')).color"
    )
    assert danger.lower() == "#ff7896" and restart == "rgb(255, 120, 150)", restart
