"""Invite links: one tap from a partner's chat into the right screen.

The three two-partner features used to hand out six-character codes drawn
from one alphabet, typed at three different doors. These cover the link that
replaced them, in both shapes it can take.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot import invites
from vechnost_bot.config import settings

CODE = "AB23CD"


@pytest.fixture
def bot_only():
    """A deployment with a bot username but no Mini App short name."""
    with (
        patch.object(settings, "bot_username", "vechnost_bot"),
        patch.object(settings, "webapp_short_name", None),
    ):
        yield


@pytest.fixture
def direct_link():
    """A deployment where BotFather knows the Mini App by name."""
    with (
        patch.object(settings, "bot_username", "vechnost_bot"),
        patch.object(settings, "webapp_short_name", "app"),
    ):
        yield


def test_without_a_short_name_the_link_goes_through_the_bot(bot_only):
    assert invites.invite_url("s69", CODE) == (
        f"https://t.me/vechnost_bot?start=s69_{CODE}"
    )


def test_with_a_short_name_the_link_opens_the_app_itself(direct_link):
    """One tap instead of two: Telegram hands the payload to the page."""
    assert invites.invite_url("cmp", CODE) == (
        f"https://t.me/vechnost_bot/app?startapp=cmp_{CODE}"
    )


def test_no_bot_username_means_no_link_rather_than_a_broken_one():
    with patch.object(settings, "bot_username", None):
        assert invites.invite_url("duo", CODE) is None


def test_each_feature_has_its_own_door(bot_only):
    urls = {kind: invites.invite_url(kind, CODE) for kind in invites.INVITE_SCREENS}
    assert len(set(urls.values())) == 3, "a link must not open the wrong feature"


def test_an_unknown_feature_is_a_programming_error():
    with pytest.raises(KeyError):
        invites.invite_param("nope", CODE)


@pytest.mark.parametrize(
    "param,expected",
    [
        (f"s69_{CODE}", ("steps69", CODE)),
        (f"cmp_{CODE}", ("compat", CODE)),
        (f"duo_{CODE}", ("coop", CODE)),
        (f"s69_{CODE.lower()}", ("steps69", CODE)),
    ],
)
def test_a_link_payload_names_a_screen_and_a_code(param, expected):
    assert invites.parse_invite_param(param) == expected


@pytest.mark.parametrize(
    "param",
    [
        None,
        "",
        "ref_ABCDEF",          # a referral, which /start also carries
        "activate_ABCDEF",     # a certificate, likewise
        "s69_TOOLONGCODE",
        "s69_AB1",             # too short
        "s69_AB1OCD",          # 1, O and I are not in the code alphabet
        "s69_../../etc",
        "s69",
    ],
)
def test_anything_else_is_not_an_invite(param):
    assert invites.parse_invite_param(param) is None


def test_the_bot_button_carries_the_screen_and_the_code():
    with patch.object(settings, "webapp_url", "https://example.com/app"):
        url = settings.webapp_join_url("steps69", CODE)
    assert url == f"https://example.com/app?screen=steps69&code={CODE}"


def test_no_mini_app_url_means_no_join_url():
    with patch.object(settings, "webapp_url", None):
        assert settings.webapp_join_url("steps69", CODE) is None


# ---------------------------------------------------------------------------
# /start answering an invite link
# ---------------------------------------------------------------------------

def _update(param):
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    update.effective_user = MagicMock(
        id=42, username="bob", first_name="Bob", last_name=None, language_code="ru"
    )
    update.effective_chat = MagicMock(id=42)
    context = MagicMock()
    context.args = [param] if param else []
    return update, context


def _run_start(update, context):
    import asyncio

    from vechnost_bot.handlers import start_command

    asyncio.run(start_command(update, context))


def test_start_answers_an_invite_with_one_button_into_the_app():
    update, context = _update(f"s69_{CODE}")
    with patch.object(settings, "webapp_url", "https://example.com/app"):
        _run_start(update, context)

    update.message.reply_text.assert_awaited_once()
    markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert len(buttons) == 1
    assert buttons[0].web_app.url.endswith(f"screen=steps69&code={CODE}")
    # The greeting is 1500 characters of manifesto; whoever followed a link
    # came to join a game, so they get the game and not the manifesto.
    update.message.reply_photo.assert_not_awaited()


def test_without_a_mini_app_an_invite_still_lands_on_the_welcome_screen():
    """Never a dead end: no app configured means the ordinary /start."""
    update, context = _update(f"cmp_{CODE}")
    with patch.object(settings, "webapp_url", None):
        _run_start(update, context)

    text = update.message.reply_text.await_args.kwargs.get("parse_mode")
    assert text == "HTML", "the welcome screen, not the invite button"


# ---------------------------------------------------------------------------
# The code is the credential
# ---------------------------------------------------------------------------

def test_a_code_is_long_enough_that_guessing_is_not_a_strategy():
    """A code is the whole credential for joining: whoever holds one takes
    the second seat, sees the couple's board or their compatibility answers,
    and locks the real partner out. Six characters was 32^6, about a billion
    — patience, not luck. Nobody types a code any more, so length is free."""
    assert invites.CODE_LENGTH >= 16
    assert len(invites.new_code()) == invites.CODE_LENGTH
    assert len(invites.CODE_ALPHABET) == 32


def test_two_codes_are_not_the_same_code():
    assert len({invites.new_code() for _ in range(200)}) == 200


def test_a_code_avoids_the_characters_people_misread():
    """Nobody types one now, but a code still gets read off a screen when
    something has gone wrong and someone is describing it out loud. The
    alphabet drops the four that get confused in pairs: 0/O and 1/I."""
    assert not (set(invites.CODE_ALPHABET) & set("01OI"))


def test_codes_minted_before_the_change_still_work():
    """They are in the database and in links already sent."""
    assert invites.valid_code("AB23CD") is True
    assert invites.parse_invite_param("s69_AB23CD") == ("steps69", "AB23CD")


def test_nothing_but_a_code_travels_in_a_link():
    assert invites.valid_code("ABC") is False
    assert invites.valid_code("A" * 17) is False
    assert invites.valid_code("AB12CD") is False        # 1 is not in the alphabet
    assert invites.valid_code("../../etc") is False
    assert invites.parse_invite_param("s69_../../etc") is None


def test_all_three_doors_mint_from_the_same_generator():
    """Three copies of one generator drift. They already differed from the
    one in referrals.py, which is a separate thing and stays separate."""
    from vechnost_bot.payments import compat_api, rooms, steps69_api

    for mint in (rooms._generate_room_code, compat_api._generate_code,
                 steps69_api._generate_code):
        code = mint()
        assert len(code) == invites.CODE_LENGTH
        assert invites.valid_code(code)
