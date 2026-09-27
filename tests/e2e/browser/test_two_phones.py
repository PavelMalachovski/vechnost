"""The Mini App on two phones, driven the way two people drive it.

The API suites prove the server keeps its rules. These prove the app keeps
them too, end to end: that the invite link the creator's screen shows is
one the partner's app can open, that the partner lands on the right screen
without typing anything, that the waiting phone catches up through its poll
without a reload, and that neither phone shows a deal meant for the other.
"""

from __future__ import annotations

import pytest

from vechnost_bot import steps69
from vechnost_bot.compat import TOTAL_QUESTIONS

from ..harness import Server, code_from_invite

YOUR_TURN = "✨ Твой ход"
POLL = 12_000  # the app polls every ~2.5 s and backs off on errors
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
            arg=before, timeout=POLL,
        )
        # The waiting phone's button refuses without asking the server.
        waiter.page.click("#btnNext")
        assert card_text(waiter) == before

        mover.page.click("#btnNext")
        mover.page.wait_for_function(
            "t => document.querySelector('#stage .card.top .q-text')?.innerText.trim() !== t",
            arg=before, timeout=POLL,
        )
        after = card_text(mover)
        waiter.page.wait_for_function(
            "t => document.querySelector('#stage .card.top .q-text')?.innerText.trim() === t",
            arg=after, timeout=POLL,
        )
        waiter.page.wait_for_function(
            "t => document.querySelector('#turnChipText')?.innerText.trim() === t",
            arg=YOUR_TURN, timeout=POLL,
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
                assert phone.text("#compatProgressNum") == f"{number} / {TOTAL_QUESTIONS}"
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
    a.screen("s69")
    a.page.locator("#s69Suits button").first.click()
    a.page.click("#btnS69Duo")
    a.screen("s69Invite")
    invite = a.text("#s69Code")
    code = code_from_invite(invite)
    a.shot("invite")

    b = phones(bob, start_param=f"s69_{code}")
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
            arg=YOUR_TURN, timeout=POLL,
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
            arg=cell["title"], timeout=POLL,
        )
        mover.shot(f"roll{roll + 1}")
        # The waiting phone catches up, and never shows the mover's secret.
        waiter.page.wait_for_function(
            "t => document.querySelector('#s69TurnChip')?.innerText.trim() === t",
            arg=YOUR_TURN, timeout=POLL,
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
    c.page.wait_for_selector("#toast.show", timeout=POLL)
    c.shot("refused")
    assert c.text("#toast"), "the refusal is said, not silent"
