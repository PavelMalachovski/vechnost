"""What Tribute tells the server about a couple, in the order it arrives.

Access decides what two people can open together: a paid creator's room is
the whole deck for both phones, an unpaid one's is the preview, and only a
paid player can start the compatibility test or the board. Tribute delivers
late, more than once and out of order - it retries a failed delivery for
about a day, so a purchase can land after its own refund - and every one of
those used to be able to hand access back (backend audit B-07, B-08) or
take a paid month away (B-09).

These play the deliveries as they come, signed with the Tribute key, and
then ask the app what each partner can do. They run in-process and against
a live server alike (CI: PostgreSQL). The gift, which needs the bot, is in
test_duo_bot.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vechnost_bot.freemium import FREE_CARDS_PER_DECK

from .harness import Player, Server

DECK = {"theme": "Acquaintance", "level": 1, "type": "questions"}


def paid(player: Player) -> bool:
    return player.ok("GET", "/api/questions?lang=ru")["access"]["paid"]


def shared_deck(creator: Player, guest: Player) -> int:
    """How many cards a room the creator opens now shows the partner."""
    code = creator.ok("POST", "/api/rooms?lang=ru", DECK)["code"]
    guest.ok("POST", f"/api/rooms/{code}/join")
    return guest.ok("GET", f"/api/rooms/{code}")["total"]


def test_a_refund_holds_against_the_purchase_delivered_again(server: Server) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    purchase = server.webhook_body("new_digital_product", alice)
    assert server.deliver(purchase).json()["action"] == "grant"
    assert shared_deck(alice, bob) > FREE_CARDS_PER_DECK, "one payment opens the deck for both"

    refund = server.deliver(server.webhook_body("digital_product_refunded", alice))
    assert refund.json()["action"] == "revoke"

    retry = server.deliver(server.redelivery(purchase), label="Tribute's retry of the purchase")
    assert retry.status_code == 200
    assert "already processed" in retry.json()["message"]
    assert paid(alice) is False
    assert shared_deck(alice, bob) == FREE_CARDS_PER_DECK, "the partner is back to the preview"
    assert alice.status("POST", "/api/compat") == 402


def test_a_purchase_first_delivered_after_its_refund_buys_nothing(server: Server) -> None:
    """The purchase's first attempt failed, the customer was refunded, and
    then Tribute's retry of the purchase got through."""
    alice = server.player("Alice")
    purchase = server.webhook_body("new_digital_product", alice)
    server.deliver(server.webhook_body("digital_product_refunded", alice))

    late = server.deliver(purchase, label="the purchase, a day late")
    assert late.status_code == 200
    assert late.json()["message"] == "Stale event ignored"
    assert late.json()["action"] == "ignore"
    assert paid(alice) is False
    assert alice.status("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"}) == 402


def test_a_new_purchase_after_a_refund_counts_and_the_old_refund_cannot_undo_it(
    server: Server,
) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    earlier = datetime.now(UTC) - timedelta(minutes=10)
    server.deliver(server.webhook_body("new_digital_product", alice, created_at=earlier))
    refund = server.webhook_body(
        "digital_product_refunded", alice, created_at=earlier + timedelta(minutes=1)
    )
    server.deliver(refund)
    server.deliver(server.webhook_body("new_digital_product", alice))
    assert paid(alice) is True, "bought again"

    again = server.deliver(server.redelivery(refund), label="the old refund, again")
    assert "already processed" in again.json()["message"]
    chargeback = server.deliver(
        server.webhook_body("chargeback", alice, created_at=earlier + timedelta(minutes=2)),
        label="a chargeback of the first purchase, late",
    )
    assert chargeback.json()["action"] == "ignore"
    assert paid(alice) is True
    assert shared_deck(alice, bob) > FREE_CARDS_PER_DECK


def test_a_cancelled_subscription_keeps_the_month_that_was_paid_for(server: Server) -> None:
    alice = server.player("Alice")
    bob = server.player("Bob")
    paid_until = (datetime.now(UTC) + timedelta(days=20)).isoformat()
    server.deliver(
        server.webhook_body("new_subscription", alice, subscription_id=7701, expires_at=paid_until)
    )
    cancel = server.deliver(
        server.webhook_body(
            "cancelled_subscription", alice, subscription_id=7701, expires_at=paid_until
        )
    )
    assert cancel.json()["action"] == "cancel"
    assert paid(alice) is True, "the renewal is off, the month is still paid for"
    code = alice.ok("POST", "/api/steps69", {"mode": "duo", "piece": "hearts"})["code"]
    assert bob.ok("POST", f"/api/steps69/{code}/join", {})["started"] is True

    server.deliver(server.webhook_body("refund", alice, subscription_id=7701))
    assert paid(alice) is False, "money back ends it at once"
