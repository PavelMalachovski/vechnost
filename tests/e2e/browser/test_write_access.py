"""Permission to message, asked once where a partner is involved.

A partner who came in through an invite and never opened a chat with the
bot cannot be told that the test's result is ready or that the board waits
for them, and a creator in the same position never hears that the partner
came. So the app asks - on a game with a partner, only of someone the bot
cannot already write to, once a month at most - and Telegram's own
`requestWriteAccess` does the rest.
"""

from __future__ import annotations

from ..harness import Server, code_from_invite


def calls(phone) -> list[list[str]]:
    return phone.page.evaluate("() => window.__tg.calls")


def test_a_guest_the_bot_cannot_reach_is_asked_once(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob", allows_write=False)
    test = alice.ok("POST", "/api/compat", None)

    phone = phones(bob, start_param=f"cmp_{test['code']}")
    phone.page.wait_for_selector("#writeAsk.show")
    phone.shot("asked")
    phone.page.click("#writeAskYes")
    phone.page.wait_for_selector("#writeAsk", state="hidden")
    assert ["requestWriteAccess"] in calls(phone)

    # The same phone, the app opened again: not asked a second time.
    phone.page.reload()
    phone.screen("compatQuiz")
    phone.page.wait_for_timeout(800)
    assert not phone.page.is_visible("#writeAsk")


def test_not_now_is_an_answer_too(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob", allows_write=False)
    room = alice.ok(
        "POST", "/api/rooms?lang=ru", {"theme": "Acquaintance", "level": 1, "type": "questions"}
    )
    code = code_from_invite(room["invite_url"])

    phone = phones(bob, start_param=f"duo_{code}")
    phone.page.wait_for_selector("#writeAsk.show")
    phone.page.click("#writeAskNo")
    phone.page.wait_for_selector("#writeAsk", state="hidden")
    assert ["requestWriteAccess"] not in calls(phone)
    phone.screen("deck")


def test_someone_the_bot_can_already_write_to_is_never_asked(server: Server, phones) -> None:
    alice = server.player("Alice", paid=True)  # allows_write_to_pm: true
    phone = phones(alice)
    phone.screen("home")
    phone.page.click("#btnCompat")
    phone.screen("compat")
    phone.page.click("#btnCompatCreate")
    phone.screen("compatInvite")
    phone.page.wait_for_timeout(800)
    assert not phone.page.is_visible("#writeAsk")
