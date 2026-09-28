"""The pair, the invitation and the push behind every invite link.

Taking the empty seat in a room, a compatibility test or a «69 ступеней»
board does three things (`payments/partners.py`): the two become each
other's partner, a newcomer is credited to whoever sent the link - it counts,
it prices nothing - and the creator hears from the bot that the partner
came. `POST /api/me` gives a person who only ever opens the app a row of
their own, which is what all three are recorded on.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient
from telegram.error import Forbidden

import vechnost_bot.payments.database as database
from tests.test_webapp_auth import make_init_data
from tests.wording import plain
from vechnost_bot.config import settings
from vechnost_bot.payments import partner_notify
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.partners import Seated
from vechnost_bot.payments.repositories import UserRepository
from vechnost_bot.payments.web import app

TOKEN = "1234567890:TEST_TOKEN_FOR_UNIT_TESTS"


def person(user_id: int, name: str, **extra) -> dict[str, str]:
    """The Authorization header of a signed Mini App user."""
    user = {
        "id": user_id,
        "first_name": name,
        "username": name.lower(),
        "language_code": "ru",
        "allows_write_to_pm": False,
        **extra,
    }
    return {"Authorization": f"tma {make_init_data(TOKEN, user=user)}"}


ALICE, BOB, CAROL = 5_100_001, 5_100_002, 5_100_003


@pytest.fixture
def pushes():
    with patch.object(partner_notify, "notify_partner_joined", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def client(tmp_path, pushes):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'pairs.db'}"),
        patch.object(settings, "enable_payment", False),
        patch.object(settings, "telegram_bot_token", TOKEN),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        yield TestClient(app)


def read(client, fn):
    """Run a repository read on the app's own loop and database."""

    async def go():
        async with get_db() as session:
            return await fn(session)

    return client.portal.call(go) if client.portal else None


def user(client, user_id):
    with client:
        return read(client, lambda s: UserRepository.get_by_telegram_id(s, user_id))


def room(client, headers):
    return client.post(
        "/api/rooms?lang=ru",
        headers=headers,
        json={"theme": "Acquaintance", "level": 1, "type": "questions"},
    ).json()["code"]


# ---------------------------------------------------------------------------
# POST /api/me
# ---------------------------------------------------------------------------


def test_the_app_gives_a_person_a_row_at_boot(client):
    with client:
        answer = client.post("/api/me", headers=person(ALICE, "Alice")).json()
        assert answer == {"can_write": False, "partner": None}
        row = read(client, lambda s: UserRepository.get_by_telegram_id(s, ALICE))
        assert (row.first_name, row.username, row.language) == ("Alice", "alice", "ru")

        # A second boot brings the name up to date and makes no second row.
        client.post("/api/me", headers=person(ALICE, "Alisa"))
        row = read(client, lambda s: UserRepository.get_by_telegram_id(s, ALICE))
        assert row.first_name == "Alisa"


def test_the_app_is_told_whether_the_bot_may_write(client):
    with client:
        allowed = person(ALICE, "Alice", allows_write_to_pm=True)
        assert client.post("/api/me", headers=allowed).json()["can_write"] is True


def test_a_boot_that_may_be_written_to_makes_the_person_reachable(client):
    """`allows_write_to_pm` is Telegram saying the bot may write: someone the
    daily card could not reach before is reached from now on. A boot without
    it changes nothing - a real send is what finds out."""

    async def unreachable(session):
        await UserRepository.ensure(session, ALICE, first_name="Alice")
        await UserRepository.ensure(session, BOB, first_name="Bob")
        await UserRepository.set_can_message(session, ALICE, False)
        await UserRepository.set_can_message(session, BOB, False)

    with client:
        read(client, unreachable)
        client.post("/api/me", headers=person(ALICE, "Alice", allows_write_to_pm=True))
        client.post("/api/me", headers=person(BOB, "Bob"))
        alice = read(client, lambda s: UserRepository.get_by_telegram_id(s, ALICE))
        bob = read(client, lambda s: UserRepository.get_by_telegram_id(s, BOB))
    assert (alice.can_message, bob.can_message) == (True, False)


def test_an_unsigned_boot_is_refused(client):
    with client:
        assert client.post("/api/me").status_code == 401
        assert client.post("/api/me", headers={"Authorization": "tma forged"}).status_code == 401


# ---------------------------------------------------------------------------
# The pair
# ---------------------------------------------------------------------------


def test_taking_a_seat_makes_two_people_partners(client, pushes):
    with client:
        client.post("/api/me", headers=person(ALICE, "Alice"))
        code = room(client, person(ALICE, "Alice"))
        client.post(f"/api/rooms/{code}/join", headers=person(BOB, "Bob"))

        assert client.post("/api/me", headers=person(ALICE, "Alice")).json()["partner"] == {
            "name": "Bob"
        }
        assert client.post("/api/me", headers=person(BOB, "Bob")).json()["partner"] == {
            "name": "Alice"
        }


@pytest.mark.parametrize("door", ["room", "compat", "steps69"])
def test_every_door_pairs_and_tells_the_creator(client, pushes, door):
    alice, bob = person(ALICE, "Alice"), person(BOB, "Bob")
    with client:
        if door == "room":
            code = room(client, alice)
            client.post(f"/api/rooms/{code}/join", headers=bob)
        elif door == "compat":
            code = client.post("/api/compat", headers=alice).json()["code"]
            client.post(f"/api/compat/{code}/join", headers=bob)
        else:
            code = client.post(
                "/api/steps69?lang=ru", headers=alice, json={"mode": "duo", "piece": "hearts"}
            ).json()["code"]
            client.post(f"/api/steps69/{code}/join", headers=bob, json={})
        partner = read(client, lambda s: UserRepository.partner_of(s, ALICE))
    assert partner.telegram_user_id == BOB
    screen = {"room": "coop", "compat": "compat", "steps69": "steps69"}[door]
    pushes.assert_awaited_once_with(
        Seated(screen=screen, code=code, creator_id=ALICE, guest_name="Bob")
    )


def test_the_creator_is_told_once_not_on_every_reopening(client, pushes):
    alice, bob = person(ALICE, "Alice"), person(BOB, "Bob")
    with client:
        code = room(client, alice)
        client.post(f"/api/rooms/{code}/join", headers=bob)
        client.post(f"/api/rooms/{code}/join", headers=bob)  # the partner reopening the link
        client.post(f"/api/rooms/{code}/join", headers=alice)  # the creator reopening their room
    assert pushes.await_count == 1


def test_the_latest_partner_is_the_partner(client, pushes):
    with client:
        client.post(
            f"/api/rooms/{room(client, person(ALICE, 'Alice'))}/join", headers=person(BOB, "Bob")
        )
        client.post(
            f"/api/rooms/{room(client, person(ALICE, 'Alice'))}/join",
            headers=person(CAROL, "Carol"),
        )
        assert read(client, lambda s: UserRepository.partner_of(s, ALICE)).telegram_user_id == CAROL
        assert read(client, lambda s: UserRepository.partner_of(s, BOB)).telegram_user_id == ALICE


def test_forgetting_a_person_takes_them_out_of_the_other_s_pair(client, pushes):
    with client:
        client.post(
            f"/api/rooms/{room(client, person(ALICE, 'Alice'))}/join", headers=person(BOB, "Bob")
        )

        async def erase(session):
            return await UserRepository.erase(session, BOB)

        removed = read(client, erase)
        assert removed["partners_unlinked"] == 1
        alice = read(client, lambda s: UserRepository.get_by_telegram_id(s, ALICE))
        assert (alice.partner_telegram_user_id, alice.partner_since) == (None, None)


# ---------------------------------------------------------------------------
# The invitation: it counts, it prices nothing
# ---------------------------------------------------------------------------


def test_a_newcomer_seated_by_an_invite_is_credited_to_the_inviter(client, pushes):
    with client:
        client.post("/api/me", headers=person(BOB, "Bob"))  # Bob opens the app, new
        client.post(
            f"/api/rooms/{room(client, person(ALICE, 'Alice'))}/join", headers=person(BOB, "Bob")
        )
        bob = read(client, lambda s: UserRepository.get_by_telegram_id(s, BOB))
        assert bob.referred_by == ALICE
        # Counted, not priced: the referral page reads `referred_at`.
        assert bob.referred_at is None
        assert read(client, lambda s: UserRepository.is_referred(s, BOB)) is False
        assert read(client, lambda s: UserRepository.count_referrals(s, ALICE)) == 1


def test_someone_who_was_already_here_is_not_anybody_s_invitation(client, pushes):
    with client:

        async def old_bob(session):
            row = await UserRepository.ensure(session, BOB, first_name="Bob")
            row.created_at = datetime.utcnow() - timedelta(days=3)

        read(client, old_bob)
        client.post(
            f"/api/rooms/{room(client, person(ALICE, 'Alice'))}/join", headers=person(BOB, "Bob")
        )
        assert read(client, lambda s: UserRepository.get_by_telegram_id(s, BOB)).referred_by is None


def test_the_first_invitation_keeps_the_credit(client, pushes):
    with client:
        client.post(
            f"/api/rooms/{room(client, person(ALICE, 'Alice'))}/join", headers=person(BOB, "Bob")
        )
        client.post(
            f"/api/rooms/{room(client, person(CAROL, 'Carol'))}/join", headers=person(BOB, "Bob")
        )
        assert (
            read(client, lambda s: UserRepository.get_by_telegram_id(s, BOB)).referred_by == ALICE
        )

        # And a `ref_` link after it changes nothing either.
        async def carol_s_link(session):
            code = await UserRepository.ensure_referral_code(session, CAROL)
            return await UserRepository.record_referral(session, BOB, code)

        assert read(client, carol_s_link) is False


def test_following_your_own_link_credits_nobody(client, pushes):
    with client:

        async def self_invite(session):
            await UserRepository.ensure(session, ALICE, first_name="Alice")
            return await UserRepository.record_invite(session, ALICE, ALICE)

        assert read(client, self_invite) is False


# ---------------------------------------------------------------------------
# The push itself
# ---------------------------------------------------------------------------


def test_the_push_names_the_partner_in_words_with_no_gender():
    seated = Seated(screen="coop", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name="Bob")
    assert plain(partner_notify.message_for(seated)) == "Bob в игре. Ваш ход!"
    nameless = Seated(screen="steps69", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name=" ")
    assert plain(partner_notify.message_for(nameless)) == (
        "Партнёр в игре «69 ступеней». Кубик ждёт вас."
    )
    assert "Результат придёт" in partner_notify.message_for(
        Seated(screen="compat", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name="Bob")
    )


async def test_the_push_carries_a_button_back_into_that_game():
    bot = AsyncMock()
    seated = Seated(screen="compat", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name="Bob")
    with (
        patch.object(partner_notify, "_bot", return_value=bot),
        patch.object(
            partner_notify, "_language", AsyncMock(return_value=partner_notify.Language.RUSSIAN)
        ),
        patch.object(settings, "webapp_url", "https://example.com/app/"),
    ):
        bot.__aenter__.return_value = bot
        await partner_notify.notify_partner_joined(seated)
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == ALICE
    (button,) = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert button.web_app.url == "https://example.com/app/?screen=compat&code=ABCDEFGHJKLMNPQR"


async def test_a_creator_with_no_chat_is_simply_not_told():
    bot = AsyncMock()
    bot.__aenter__.return_value = bot
    bot.send_message.side_effect = Forbidden("bot can't initiate conversation with a user")
    seated = Seated(screen="coop", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name="Bob")
    with (
        patch.object(partner_notify, "_bot", return_value=bot),
        patch.object(
            partner_notify, "_language", AsyncMock(return_value=partner_notify.Language.RUSSIAN)
        ),
    ):
        await partner_notify.notify_partner_joined(seated)  # does not raise


async def test_nothing_on_the_way_raises_or_logs_the_code(caplog):
    """It runs after the join has answered: a dead database or network costs
    the creator one message, never the partner their seat, and the code - a
    seat in somebody's game - stays out of the log."""
    bot = AsyncMock()
    bot.__aenter__.return_value = bot
    bot.send_message.side_effect = RuntimeError("network down")
    seated = Seated(screen="coop", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name="Bob")
    with (
        patch.object(partner_notify, "_bot", return_value=bot),
        patch.object(database, "get_db", side_effect=RuntimeError("database down")),
    ):
        await partner_notify.notify_partner_joined(seated)
    # The language could not be read: Russian, the only one there is.
    assert plain(bot.send_message.await_args.kwargs["text"]) == "Bob в игре. Ваш ход!"
    assert "network down" in caplog.text
    assert "ABCDEFGHJKLMNPQR" not in caplog.text


async def test_without_a_token_nobody_is_told():
    seated = Seated(screen="coop", code="ABCDEFGHJKLMNPQR", creator_id=ALICE, guest_name="Bob")
    with patch.object(settings, "telegram_bot_token", ""):
        assert partner_notify._bot() is None
        await partner_notify.notify_partner_joined(seated)
