"""What /stats counts, played out by two people against the real app.

Every count comes from somewhere a person really did something: the bot's
/start with its link, the app's own reports, a seat taken, a test finished,
a payment Tribute confirmed. These check that each lands in `events` once,
as a name and one token - never a code, never a text - that a client
cannot report what only the server may, and that /delete_me takes a
person's counts with them.
"""

from __future__ import annotations

import pytest

from vechnost_bot import stats
from vechnost_bot.compat import TOTAL_QUESTIONS

from .harness import Server, code_from_invite

pytestmark = pytest.mark.inprocess_only


def events_of(server: Server, player) -> list[tuple[str, str | None, str | None]]:
    """(name, detail, source) of every event of `player`, oldest first."""
    from sqlalchemy import select

    from vechnost_bot.payments.database import get_db
    from vechnost_bot.payments.models import AnalyticsEvent

    async def read() -> list[tuple[str, str | None, str | None]]:
        async with get_db() as session:
            rows = await session.execute(
                select(AnalyticsEvent.name, AnalyticsEvent.detail, AnalyticsEvent.source)
                .where(AnalyticsEvent.telegram_user_id == player.id)
                .order_by(AnalyticsEvent.id)
            )
            return [tuple(row) for row in rows.all()]

    return server.portal.call(read)


def names(server: Server, player) -> list[str]:
    return [name for name, _, _ in events_of(server, player)]


def test_a_couple_playing_is_counted_on_the_server(server: Server) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")

    room = alice.ok("POST", "/api/rooms?lang=ru", {"theme": "Acquaintance", "level": 1, "type": "questions"})
    bob.ok("POST", f"/api/rooms/{room['code']}/join")
    bob.ok("POST", f"/api/rooms/{room['code']}/join")  # the partner reopening the link

    test = alice.ok("POST", "/api/compat", None)
    bob.ok("POST", f"/api/compat/{test['code']}/join")
    for index in range(TOTAL_QUESTIONS):
        alice.ok("POST", f"/api/compat/{test['code']}/answer", {"index": index, "value": 4})
        bob.ok("POST", f"/api/compat/{test['code']}/answer", {"index": index, "value": 3})

    game = alice.ok("POST", "/api/steps69?lang=ru", {"mode": "duo", "piece": "hearts"})
    bob.ok("POST", f"/api/steps69/{game['code']}/join", {})

    # Alice paid through Tribute before she sat down: that is counted too.
    assert names(server, alice) == ["purchase", "room_create", "compat_create", "s69_create"]
    assert ("s69_create", "duo", None) in events_of(server, alice)
    assert names(server, bob) == ["room_join", "compat_join", "compat_done", "s69_join"]


def test_what_the_app_reports_is_a_name_and_one_token(server: Server) -> None:
    alice = server.player("Alice")

    def send(name: str, detail: str | None = None, source: str | None = None) -> int:
        return alice.status("POST", "/api/events", {"name": name, "detail": detail, "source": source})

    assert send("deck_open", "Acquaintance:1:questions") == 204
    assert send("deck_open", "a question somebody typed") == 204
    assert send("paywall_view", "room") == 204
    assert send("buy_click", "room") == 204
    assert send("invite_share", "duo") == 204
    assert send("lib_open", "dates") == 204
    # Arrivals count people, not launches: one a day, with its channel.
    assert send("app_open", None, "TikTok") == 204
    assert send("app_open", None, "instagram") == 204
    assert events_of(server, alice) == [
        ("deck_open", "Acquaintance:1:questions", None),
        ("deck_open", None, None),
        ("paywall_view", "room", None),
        ("buy_click", "room", None),
        ("invite_share", "duo", None),
        ("lib_open", "dates", None),
        ("app_open", None, "tiktok"),
    ]


def test_the_app_cannot_report_what_only_the_server_knows(server: Server) -> None:
    """A purchase, a join or a finished test is counted where it happens;
    a client claiming one is refused, and an unsigned report is not kept."""
    alice = server.player("Alice")
    for name in ("purchase", "room_join", "compat_done", "refund", "made_up"):
        assert alice.status("POST", "/api/events", {"name": name}) == 422, name
    assert names(server, alice) == []

    response = server.http.post("/api/events", json={"name": "deck_open", "detail": "Sex::questions"})
    assert response.status_code == 204


def test_money_is_counted_as_tribute_confirmed_it(server: Server) -> None:
    carol = server.player("Carol")
    server.grant(carol)
    server.revoke(carol)
    assert names(server, carol) == ["purchase", "refund"]
    assert events_of(server, carol)[0] == ("purchase", "lifetime", None)


def test_the_bot_counts_an_arrival_with_its_channel_not_its_parameter(
    server: Server, bot
) -> None:
    alice = server.player("Alice", paid=True)
    bob = server.player("Bob")
    carol = server.player("Carol")
    dave = server.player("Dave")

    bot.send(alice, "/start")
    bot.send(bob, "/start src_Blogger_Anna")
    room = alice.ok("POST", "/api/rooms?lang=ru", {"theme": "Acquaintance", "level": 1, "type": "questions"})
    bot.send(carol, f"/start duo_{code_from_invite(room['invite_url'])}")
    bot.send(dave, "/start activate_VECH-ABCD-EFGH")

    assert ("bot_start", None, None) in events_of(server, alice)
    assert events_of(server, bob) == [("bot_start", None, "blogger_anna")]
    assert events_of(server, carol) == [("bot_start", None, "invite")]
    # The certificate code is lifetime access to whoever reads it: the
    # count says a gift brought them, and nothing more.
    assert events_of(server, dave) == [("bot_start", None, "gift")]


def test_delete_me_takes_the_counts_with_it(server: Server) -> None:
    from vechnost_bot.payments.database import get_db
    from vechnost_bot.payments.repositories import UserRepository

    alice = server.player("Alice", paid=True)
    alice.ok("POST", "/api/rooms?lang=ru", {"theme": "Acquaintance", "level": 1, "type": "questions"})
    alice.status("POST", "/api/events", {"name": "lib_open", "detail": "dates"})
    assert names(server, alice) == ["purchase", "room_create", "lib_open"]

    async def erase() -> dict[str, int]:
        async with get_db() as session:
            return await UserRepository.erase(session, alice.id)

    assert server.portal.call(erase)["events"] == 3
    assert names(server, alice) == []


def test_stats_reads_the_funnel_off_what_happened(server: Server, bot) -> None:
    """Measured as a difference: on PostgreSQL the suite shares one database,
    so the report also holds every other test's people."""
    before = server.portal.call(stats.collect).windows[0]

    alice = server.player("Alice")
    bob = server.player("Bob")
    bot.send(alice, "/start src_tiktok")
    alice.status("POST", "/api/events", {"name": "deck_open", "detail": "Acquaintance:1:questions"})
    alice.status("POST", "/api/events", {"name": "paywall_view", "detail": "deck"})
    alice.status("POST", "/api/events", {"name": "buy_click", "detail": "deck"})
    server.grant(alice)
    bob.status("POST", "/api/events", {"name": "app_open"})
    bob.status("POST", "/api/events", {"name": "paywall_view", "detail": "compat"})

    result = server.portal.call(stats.collect)
    week = result.windows[0]
    assert week.new_people - before.new_people == 2
    assert week.activated - before.activated == 1
    sources_before, sources_after = dict(before.sources), dict(week.sources)
    assert sources_after.get("tiktok", 0) - sources_before.get("tiktok", 0) == 1
    assert (
        sources_after.get(stats.NO_SOURCE, 0) - sources_before.get(stats.NO_SOURCE, 0) == 1
    )
    assert week.people("paywall_view") - before.people("paywall_view") == 2
    assert week.people("buy_click") - before.people("buy_click") == 1
    assert week.people("purchase") - before.people("purchase") == 1

    text = stats.render(result)
    assert f"Новые люди: {week.new_people} / " in text
    assert "tiktok: " in text
    for secret in (alice.init_data, str(alice.id), str(bob.id)):
        assert secret not in text
