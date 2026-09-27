"""Two people and the bot: the flows that pass from one user to another.

The Mini App is where a couple plays, but a lot travels between two users
through the chat first: an invite link that the bot turns into a button, a
referral, a gift certificate bought by one person and redeemed by another,
and /delete_me, which takes rows shared with a partner along with the
person asking. Here the real application from `bot.create_application()`
handles every update, with a fake Telegram on the other end of the wire,
and the API is asked afterwards whether the other user saw the effect.
"""

from __future__ import annotations

import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from vechnost_bot.compat import TOTAL_QUESTIONS
from vechnost_bot.config import settings
from vechnost_bot.i18n import get_text
from vechnost_bot.privacy import CONFIRM

from .harness import E2E_WEBAPP_URL, Server, code_from_invite

pytestmark = pytest.mark.inprocess_only

GIFT_CODE = re.compile(r"VECH-[A-Z0-9]{4}-[A-Z0-9]{4}")


def paid(player) -> bool:
    return player.ok("GET", "/api/questions?lang=ru")["access"]["paid"]


def test_two_people_start_the_bot_at_once_and_each_hears_only_their_own(
    server: Server, bot
) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    bot.send(alice, "/start")
    bot.send(bob, "/start")

    for player in (alice, bob):
        sent = server.telegram.to(player.id)
        assert [s.method for s in sent] == ["sendphoto", "sendmessage"], sent
        greeting = sent[-1]
        assert greeting.text, "the greeting is not empty"
        urls = [b.get("web_app", {}).get("url") for b in greeting.buttons()]
        assert any(url and url.startswith(E2E_WEBAPP_URL) for url in urls), (
            "the welcome screen has the one button into the app"
        )
    assert server.telegram.texts_to(alice.id) == server.telegram.texts_to(bob.id)


@pytest.mark.parametrize("kind, path, screen", [
    ("cmp", "/api/compat", "compat"),
    ("duo", "/api/rooms", "coop"),
    ("s69", "/api/steps69", "steps69"),
])
def test_an_invite_through_the_bot_becomes_a_button_that_seats_the_partner(
    server: Server, bot, kind: str, path: str, screen: str
) -> None:
    """Without a Mini App short name the link opens the chat; the bot must
    answer with a button that carries the code into the right screen."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    body = {
        "cmp": None,
        "duo": {"theme": "Acquaintance", "level": 1, "type": "questions"},
        "s69": {"mode": "duo", "piece": "clubs"},
    }[kind]
    state = alice.ok("POST", f"{path}?lang=ru", body)
    invite = state["invite_url"]
    assert f"?start={kind}_" in invite, invite

    bot.send(bob, f"/start {kind}_{code_from_invite(invite)}")
    answer = server.telegram.to(bob.id)[-1]
    [button] = answer.buttons()
    url = button["web_app"]["url"]
    query = parse_qs(urlsplit(url).query)
    assert query["screen"] == [screen]
    code = query["code"][0]
    assert code == state["code"]

    join_body = {} if kind == "s69" else None
    joined = bob.ok("POST", f"{path}/{code}/join?lang=ru", join_body)
    assert joined["started"] is True and joined["your_role"] == "guest"


def test_a_referral_passes_from_one_user_to_the_next(server: Server, bot) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    discounted = "https://tribute.invalid/discount"
    with patch.object(settings, "referral_payment_url", discounted):
        bot.send(alice, "/invite")
        link = re.search(r"https://t\.me/\S+", server.telegram.texts_to(alice.id)[-1]).group(0)
        param = parse_qs(urlsplit(link).query)["start"][0]

        # Her own link does not discount her.
        bot.send(alice, f"/start {param}")
        assert paid(alice) is False
        assert alice.ok("GET", "/api/questions")["access"]["payment_url"] != discounted

        bot.send(bob, f"/start {param}")
        assert get_text(
            "referral.welcome", percent=settings.referral_discount_percent
        ) in server.telegram.texts_to(bob.id)
        access = bob.ok("GET", "/api/questions")["access"]
        assert access["payment_url"] == discounted
        assert access["discount_percent"] == settings.referral_discount_percent

        bot.send(alice, "/invite")
        assert "Уже пришли по ссылке: 1" in server.telegram.texts_to(alice.id)[-1]


def test_a_gift_bought_by_one_user_unlocks_the_other(server: Server, bot) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    with patch.object(settings, "gift_product_id", "777"):
        server.webhook("new_digital_product", alice, product_id=777)

    [card] = [s for s in server.telegram.to(alice.id) if GIFT_CODE.search(s.text)]
    code = GIFT_CODE.search(card.text).group(0)
    assert paid(alice) is False, "a gift is a certificate to hand on, not the buyer's access"

    bot.send(bob, f"/activate {code}")
    assert paid(bob) is True
    assert get_text("certificate.activated") in server.telegram.texts_to(bob.id)

    bot.send(alice, f"/start activate_{code}")
    assert get_text("certificate.already_used") in server.telegram.texts_to(alice.id)
    assert paid(alice) is False


def test_delete_me_takes_the_shared_rows_for_both(server: Server, bot) -> None:
    """One row per couple, and consent to keep it has to be unanimous."""
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob", paid=True)
    room = alice.ok("POST", "/api/rooms", {"theme": "Acquaintance", "level": 1, "type": "questions"})["code"]
    bob.ok("POST", f"/api/rooms/{room}/join")
    test = alice.ok("POST", "/api/compat")["code"]
    bob.ok("POST", f"/api/compat/{test}/join")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{test}/answer", {"index": index, "value": 3})
        bob.ok("POST", f"/api/compat/{test}/answer", {"index": index, "value": 4})
    game = bob.ok("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"})["code"]
    alice.ok("POST", f"/api/steps69/{game}/join", {})
    bob.ok("POST", f"/api/steps69/{game}/roll")

    bot.send(alice, "/start")
    bot.send(alice, "/delete_me")
    question = server.telegram.to(alice.id)[-1]
    assert CONFIRM in [b.get("callback_data") for b in question.buttons()]
    bot.press(alice, question, CONFIRM)
    assert server.telegram.to(alice.id)[-1].text == get_text("privacy.done")

    assert bob.status("GET", f"/api/rooms/{room}") == 404
    assert bob.status("GET", f"/api/compat/{test}") == 404
    assert bob.status("GET", "/api/compat/mine") == 404
    assert bob.status("GET", f"/api/steps69/{game}") == 404
    assert bob.status("GET", "/api/steps69/mine") == 404
    assert paid(bob) is True, "the partner keeps their own access"
    assert paid(alice) is False, "access does not come back after erasure"
