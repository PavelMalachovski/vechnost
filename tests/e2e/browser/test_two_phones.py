"""The Mini App on two phones, driven the way two people drive it.

The API suites prove the server keeps its rules. These prove the app keeps
them too, end to end: that the invite link the creator's screen shows is
one the partner's app can open, that the partner lands on the right screen
without typing anything, that the waiting phone catches up through its poll
without a reload, and that neither phone shows a deal meant for the other.

Each scenario runs on both phone models (conftest.py): two Android phones in
Chromium, and two iPhones in WebKit.
"""

from __future__ import annotations

import pytest

from vechnost_bot import steps69
from vechnost_bot.compat import TOTAL_QUESTIONS

from ..harness import Server, code_from_invite

YOUR_TURN = "✨ Ваш ход"
POLL = 12_000  # the app polls every ~2.5 s and backs off on errors

# What a refused tap does to the waiting phone, recorded as it happens: the
# card's `wobble` and the chip's `pulse` going on, and the animations that
# ran to their end (a cancelled one never fires `animationend`).
WATCH_THE_REFUSAL = """() => {
  const seen = window.__refusal = { marked: [], ended: [] };
  const card = document.querySelector('#stage .card.top');
  const chip = document.getElementById('turnChipText');
  for (const [el, cls] of [[card, 'wobble'], [chip, 'pulse']]) {
    new MutationObserver(() => {
      if (el.classList.contains(cls) && !seen.marked.includes(cls)) seen.marked.push(cls);
    }).observe(el, { attributes: true, attributeFilter: ['class'] });
  }
  chip.addEventListener('animationend', e => seen.ended.push(e.animationName));
}"""
SECRETS = {c.id: c.secret for c in steps69.load_cells() if c.kind == "secret"}


def card_text(phone) -> str:
    return phone.text("#stage .card.top .q-text")


def test_two_phones_share_one_deck(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
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
    assert invite.startswith("https://t.me/"), invite
    a.shot("invite")

    b = phones(bob, start_param=f"duo_{code_from_invite(invite)}")
    b.screen("deck")
    a.screen("deck", timeout=POLL)  # Alice's invite screen hears Bob arrive
    a.shot("joined")
    b.shot("joined")

    for turn in range(4):
        mover, waiter = (a, b) if turn % 2 == 0 else (b, a)
        assert mover.text("#turnChipText") == YOUR_TURN
        before = card_text(mover)
        waiter.page.wait_for_function(
            "t => document.querySelector('#stage .card.top .q-text')?.innerText.trim() === t",
            arg=before,
            timeout=POLL,
        )
        # The waiting phone says so before the tap: its button is dimmed
        # (audit D-20), the mover's is not. Tapped anyway, it refuses
        # without asking the server - the card shakes, the chip flashes.
        assert waiter.page.get_attribute("#btnNext", "aria-disabled") == "true"
        assert mover.page.get_attribute("#btnNext", "aria-disabled") == "false"
        waiter.page.evaluate(WATCH_THE_REFUSAL)
        waiter.page.click("#btnNext", force=True)
        # Both marks go on, and the chip's flash runs to its end. Watched
        # from before the tap rather than caught in the act: each lasts well
        # under a second, and a poll every 2.5 s used to rewrite the chip's
        # classes and cut the flash off - WebKit on CI sometimes missed it.
        waiter.page.wait_for_function(
            "() => window.__refusal.marked.length === 2"
            " && window.__refusal.ended.includes('chip-pulse')",
            timeout=POLL,
        )
        assert card_text(waiter) == before

        mover.page.click("#btnNext")
        mover.page.wait_for_function(
            "t => document.querySelector('#stage .card.top .q-text')?.innerText.trim() !== t",
            arg=before,
            timeout=POLL,
        )
        after = card_text(mover)
        waiter.page.wait_for_function(
            "t => document.querySelector('#stage .card.top .q-text')?.innerText.trim() === t",
            arg=after,
            timeout=POLL,
        )
        waiter.page.wait_for_function(
            "t => document.querySelector('#turnChipText')?.innerText.trim() === t",
            arg=YOUR_TURN,
            timeout=POLL,
        )
        mover.shot(f"turn{turn + 1}")
        waiter.shot(f"turn{turn + 1}")


def test_two_phones_take_the_compatibility_test(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")

    a = phones(alice)
    a.screen("home")
    a.page.click("#btnCompat")
    a.screen("compat")
    a.page.click("#btnCompatCreate")
    a.screen("compatInvite")
    invite = a.text("#compatCode")
    a.shot("invite")

    b = phones(bob, start_param=f"cmp_{code_from_invite(invite)}")
    b.screen("compatQuiz")
    a.screen("compatQuiz", timeout=POLL)

    for phone, value in ((a, "4"), (b, "2")):
        for number in range(1, TOTAL_QUESTIONS + 1):
            if number < TOTAL_QUESTIONS:
                assert phone.text("#compatProgressNum") == f"Вопрос {number} из {TOTAL_QUESTIONS}"
            phone.page.locator(
                f"#compatScale .compat-opt[data-value='{value}']:not([disabled])"
            ).click()
            if number == 1:
                phone.shot("first-answer")
    # Bob's last answer completes the test; Alice's poll brings her the result.
    b.screen("compatResult")
    a.screen("compatResult", timeout=POLL)
    a.shot("result")
    b.shot("result")
    assert a.text("#compatResultBody") == b.text("#compatResultBody"), "one result for both"
    for phone in (a, b):
        # A partner's answers are never on screen, only zones and texts.
        assert "creator_answers" not in phone.page.content()


def test_two_phones_climb_the_board(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")

    a = phones(alice)
    a.screen("home")
    a.page.click("#btnS69")
    # «69 ступеней» is 18+: the question comes before its first screen.
    a.page.wait_for_selector("#nsfw.show")
    a.page.click("#nsfwYes")
    a.screen("s69")
    a.page.locator("#s69Suits button").first.click()
    a.page.click("#btnS69Duo")
    a.screen("s69Invite")
    invite = a.text("#s69Code")
    code = code_from_invite(invite)
    a.shot("invite")

    b = phones(bob, start_param=f"s69_{code}")
    # By invite too: nobody is seated before the answer.
    b.page.wait_for_selector("#nsfw.show")
    b.page.click("#nsfwYes")
    b.screen("s69Board")
    a.screen("s69Board", timeout=POLL)
    a.shot("board")
    b.shot("board")

    by_seat = {0: (a, alice), 1: (b, bob)}
    for roll in range(6):
        state = alice.ok("GET", f"/api/steps69/{code}")
        mover, mover_player = by_seat[state["turn"]]
        waiter, _ = by_seat[1 - state["turn"]]
        mover.page.wait_for_function(
            "t => document.querySelector('#s69TurnChip')?.innerText.trim() === t",
            arg=YOUR_TURN,
            timeout=POLL,
        )
        assert waiter.text("#s69TurnChip") != YOUR_TURN
        mover.page.click("#s69Dice")
        mover.page.wait_for_function(
            "() => !document.querySelector('#s69Dice')?.classList.contains('rolling')",
            timeout=POLL,
        )
        after = mover_player.ok("GET", f"/api/steps69/{code}")
        cell = after["you"]["cell"]
        # The mover's card is the square the server says they stand on.
        mover.page.wait_for_function(
            "t => document.querySelector('#s69Cell')?.innerText.includes(t)",
            arg=cell["title"],
            timeout=POLL,
        )
        mover.shot(f"roll{roll + 1}")
        # The waiting phone catches up, and never shows the mover's secret.
        waiter.page.wait_for_function(
            "t => document.querySelector('#s69TurnChip')?.innerText.trim() === t",
            arg=YOUR_TURN,
            timeout=POLL,
        ) if not after["partner"]["home"] else None
        secret = SECRETS.get(cell["id"])
        partner_pos = after["partner"]["position"]
        if secret and partner_pos != cell["id"]:
            assert secret not in waiter.page.content(), "a secret reached the other phone"
        waiter.shot(f"roll{roll + 1}")


@pytest.mark.parametrize("kind", ["duo", "cmp", "s69"])
def test_a_link_to_a_seat_that_is_taken_says_so(server: Server, phones, kind: str) -> None:
    """A third phone opening a forwarded link is told the seat is taken."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    carol = server.player("Carol")
    path, body = {
        "duo": ("/api/rooms", {"theme": "Acquaintance", "level": 1, "type": "questions"}),
        "cmp": ("/api/compat", None),
        "s69": ("/api/steps69", {"mode": "duo", "piece": "hearts"}),
    }[kind]
    code = alice.ok("POST", path, body)["code"]
    bob.ok("POST", f"{path}/{code}/join", {} if kind == "s69" else None)

    c = phones(carol, start_param=f"{kind}_{code}")
    if kind == "s69":
        # The board is 18+: the question comes before the door is tried.
        c.page.wait_for_selector("#nsfw.show")
        c.page.click("#nsfwYes")
    c.page.wait_for_selector("#toast.show", timeout=POLL)
    c.shot("refused")
    assert c.text("#toast"), "the refusal is said, not silent"


def test_telegram_web_can_open_the_app_in_its_frame(browser, live_url: str) -> None:
    """Telegram Web shows a Mini App in an <iframe> under web.telegram.org.

    Both origins are served through Playwright routes - the parent is a page
    with the iframe, the app is the live server's own response, headers and
    all - so this checks what the engine does with the headers the server
    really sends: Chromium, and WebKit for Telegram Web in Safari. With
    `X-Frame-Options: SAMEORIGIN` the frame was refused, and Telegram Web
    users saw a blank app.
    """
    parent, app_origin = "https://web.telegram.org/k/", "https://vechnost-app.invalid"
    context = browser.new_context()
    refused: list[str] = []

    def route(route, request):
        if request.url.startswith(parent):
            route.fulfill(
                body=f'<iframe id="app" src="{app_origin}/app/" width="390" height="700"></iframe>',
                content_type="text/html",
            )
        elif request.url.startswith(app_origin):
            route.fulfill(response=route.fetch(url=request.url.replace(app_origin, live_url)))
        else:
            route.abort()

    context.route("**/*", route)
    page = context.new_page()
    page.on("console", lambda m: refused.append(m.text) if "frame" in m.text.lower() else None)
    page.goto(parent)
    frame = page.frame_locator("#app")
    frame.locator("section#home").wait_for(state="attached", timeout=10_000)
    assert not refused, refused
    context.close()
