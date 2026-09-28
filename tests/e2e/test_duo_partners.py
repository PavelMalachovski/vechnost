"""An invite, played out by two people: the pair, the credit and the push.

Alice shares a link and puts the phone down. Bob, who has never used
VECHNOST, opens it and takes the seat. The bot tells Alice that Bob is in
the game, with a button back into it; each of them now knows the other as
their partner; and Alice's /invite counts Bob - without Bob being offered a
referral price, which belongs to the `ref_` links alone.
"""

from __future__ import annotations

import pytest

from tests.wording import plain

from .harness import Server

pytestmark = pytest.mark.inprocess_only  # the pushes land in the fake Telegram


def deck() -> dict[str, object]:
    return {"theme": "Acquaintance", "level": 1, "type": "questions"}


def test_the_creator_hears_the_partner_came_and_goes_straight_back(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    room = alice.ok("POST", "/api/rooms?lang=ru", deck())
    before = len(server.telegram.to(alice.id))  # her «всё открыто» from the purchase

    bob.ok("POST", "/api/me")
    bob.ok("POST", f"/api/rooms/{room['code']}/join")

    (push,) = server.telegram.to(alice.id)[before:]
    assert plain(push.text) == "Bob в игре. Ваш ход!"
    (button,) = push.buttons()
    assert "screen=coop" in button["web_app"]["url"]
    assert room["code"] in button["web_app"]["url"]
    assert server.telegram.to(bob.id) == [], "the guest is told nothing: they are right there"

    # Opening the link again, or the creator reopening the room, says nothing more.
    bob.ok("POST", f"/api/rooms/{room['code']}/join")
    alice.ok("POST", f"/api/rooms/{room['code']}/join")
    assert len(server.telegram.to(alice.id)) == before + 1


def test_the_two_know_each_other_and_the_invitation_counts(server: Server, bot) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    bob.ok("POST", "/api/me")
    test = alice.ok("POST", "/api/compat", None)
    bob.ok("POST", f"/api/compat/{test['code']}/join")

    assert alice.ok("POST", "/api/me")["partner"] == {"name": "Bob"}
    assert bob.ok("POST", "/api/me")["partner"] == {"name": "Alice"}

    bot.send(alice, "/invite")
    assert "Уже пришли по вашим приглашениям: 1" in plain(server.telegram.texts_to(alice.id)[-1])


def test_an_invited_partner_pays_what_everyone_pays(server: Server) -> None:
    from unittest.mock import patch

    from vechnost_bot.config import settings

    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    bob.ok("POST", "/api/me")
    game = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})
    bob.ok("POST", f"/api/steps69/{game['code']}/join", {})

    with patch.object(
        settings, "referral_payment_url", "https://t.me/tribute/app?startapp=cheaper"
    ):
        access = bob.ok("GET", "/api/questions?lang=ru")["access"]
    assert "discount_percent" not in access
    assert access["payment_url"] != "https://t.me/tribute/app?startapp=cheaper"
