"""Tests for the daily self-reflection push."""

import os
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

import vechnost_bot.payments.database as database
from vechnost_bot.config import settings
from vechnost_bot.daily_card import render_daily_card, send_daily_cards
from vechnost_bot.i18n import Language
from vechnost_bot.library import question_of_the_day
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import UserRepository


def test_caption_carries_the_day_number():
    day = date(2026, 2, 16)          # day 47 of the year
    assert day.timetuple().tm_yday == 47
    _, number = question_of_the_day(47, Language.RUSSIAN)
    assert number == 47
    _, caption = render_daily_card(day, Language.RUSSIAN)
    assert "47" in caption
    assert "365" in caption


def test_same_day_renders_the_same_card():
    day = date(2026, 5, 5)
    first, _ = render_daily_card(day, Language.RUSSIAN)
    second, _ = render_daily_card(day, Language.RUSSIAN)
    assert first.getvalue() == second.getvalue()


def test_first_and_last_day_of_the_year_render():
    for day in (date(2026, 1, 1), date(2026, 12, 31)):
        image, caption = render_daily_card(day, Language.RUSSIAN)
        assert image.getvalue()
        assert caption.strip()


def test_leap_day_renders_without_raising():
    image, _ = render_daily_card(date(2028, 12, 31), Language.RUSSIAN)   # day 366
    assert image.getvalue()


def test_renders_in_russian():
    image, caption = render_daily_card(date(2026, 3, 3), Language.RUSSIAN)
    assert image.getvalue()
    assert caption.strip()


# The sends run against a real (throwaway SQLite) database: the recipients
# are read a page at a time, in id order after the run's cursor, and a mock
# repository that answers every page with the same list never lets the loop
# end.


@pytest.fixture
def db(tmp_path):
    with (
        patch.object(settings, "database_url", f"sqlite:///{tmp_path / 'daily.db'}"),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
        patch("vechnost_bot.broadcast.SECONDS_BETWEEN_SENDS", 0),
    ):
        yield


async def _people(*ids: int, opted_out: bool = False) -> None:
    async with get_db() as session:
        for user_id in ids:
            await UserRepository.create_or_update(session, telegram_user_id=user_id, language="ru")
    if opted_out:
        async with get_db() as session:
            for user_id in ids:
                await UserRepository.set_daily_card_opt_out(session, user_id, True)


def _bot(**send_photo):
    bot = MagicMock()
    bot.send_photo = AsyncMock(**send_photo)
    return bot


async def test_a_render_failure_does_not_kill_the_push(db):
    """The render sits inside the per-user loop's own try.

    It used to run before it, so a broken font or a bad day index killed the
    whole job before the first send.
    """
    await _people(1, 2)
    bot = _bot()

    with patch(
        "vechnost_bot.daily_card.render_daily_card",
        side_effect=RuntimeError("font gone"),
    ):
        sent = await send_daily_cards(bot)

    assert sent == 0
    bot.send_photo.assert_not_awaited()


async def test_healthy_recipient_gets_the_card(db):
    await _people(42)
    bot = _bot()

    sent = await send_daily_cards(bot)

    assert sent == 1
    bot.send_photo.assert_awaited_once()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["chat_id"] == 42

    image, caption = render_daily_card(datetime.now(UTC).date(), Language.RUSSIAN)
    assert kwargs["photo"] == image.getvalue()
    assert kwargs["caption"] == caption

    labels = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert "daily_off" in labels


async def test_everyone_is_reached_across_pages_and_nobody_twice(db):
    """The list is read a page at a time; the pages must meet exactly."""
    await _people(*range(1, 12))
    await _people(12, opted_out=True)
    bot = _bot()

    with patch("vechnost_bot.daily_card.RECIPIENTS_PER_PAGE", 4):
        sent = await send_daily_cards(bot)

    assert sent == 11
    assert [c.kwargs["chat_id"] for c in bot.send_photo.await_args_list] == list(range(1, 12))


async def test_a_resumed_run_starts_after_the_last_person_reached(db):
    """The cursor is the last Telegram id done: a run taken over after a
    restart carries on from there instead of starting the list again."""
    from vechnost_bot.jobs import Run

    await _people(10, 20, 30, 40)
    bot = _bot()
    run = Run.detached_for("daily_card")
    run.cursor = 20

    assert await send_daily_cards(bot, run) == 2
    assert [c.kwargs["chat_id"] for c in bot.send_photo.await_args_list] == [30, 40]
    assert run.cursor == 40 and run.sent == 2


async def test_the_card_of_the_run_s_own_day_is_sent(db):
    """A run resumed after midnight still sends the day it belongs to."""
    from vechnost_bot.jobs import Run

    await _people(7)
    bot = _bot()
    day = date(2026, 2, 16)

    await send_daily_cards(bot, Run.detached_for("daily_card", day))

    _, caption = render_daily_card(day, Language.RUSSIAN)
    assert bot.send_photo.await_args.kwargs["caption"] == caption


def test_one_door_into_the_app_and_one_way_out():
    """«Играть» and «Библиотека» were one app opened at two screens.

    They asked the reader to choose before they had seen either, so the push
    carries one button into the app and the opt-out beside it. Without a
    WEBAPP_URL there is no app to open and the button falls back to the
    bot's own deck rather than disappearing.
    """
    from vechnost_bot.config import settings
    from vechnost_bot.daily_card import _daily_keyboard

    original = settings.webapp_url
    try:
        settings.webapp_url = None
        rows = _daily_keyboard(Language.RUSSIAN).inline_keyboard
        buttons = [b for row in rows for b in row]
        assert all(b.web_app is None for b in buttons)
        assert [b.callback_data for b in buttons] == ["start_game", "daily_off"]

        settings.webapp_url = "https://example.com/app"
        rows = _daily_keyboard(Language.RUSSIAN).inline_keyboard
        buttons = [b for row in rows for b in row]
        assert len(buttons) == 2, "one way in, one way out"
        into_app = [b for b in buttons if b.web_app]
        assert len(into_app) == 1
        assert into_app[0].web_app.url == "https://example.com/app"
        assert buttons[-1].callback_data == "daily_off"
    finally:
        settings.webapp_url = original


async def test_blocked_user_is_opted_out(db):
    from telegram.error import Forbidden

    await _people(42)
    bot = _bot(side_effect=Forbidden("blocked"))

    sent = await send_daily_cards(bot)

    assert sent == 0
    async with get_db() as session:
        user = await UserRepository.get_by_telegram_id(session, 42)
        assert user.daily_card_opt_out is True


async def test_flood_control_is_waited_out_not_dropped(db):
    """The push rides the broadcast loop, so Telegram's retry_after is
    honoured and the recipient gets a second try. The old loop caught
    RetryAfter as a generic failure and moved on, which at a few thousand
    recipients meant everyone after the first flood-control reply was
    silently skipped."""
    from telegram.error import RetryAfter

    await _people(42)
    bot = _bot(side_effect=[RetryAfter(1), MagicMock()])

    with patch("vechnost_bot.broadcast.asyncio.sleep", AsyncMock()):
        sent = await send_daily_cards(bot)

    assert sent == 1
    assert bot.send_photo.await_count == 2


async def test_the_image_is_uploaded_once_and_reused_by_file_id(db):
    """Telegram hands back a file_id on the first upload; the second
    recipient gets that instead of the same hundred kilobytes again."""
    await _people(1, 2)
    reply = MagicMock()
    reply.photo = [MagicMock(file_id="AgACAgIAAxkDAAI")]
    bot = _bot(return_value=reply)

    sent = await send_daily_cards(bot)

    assert sent == 2
    first, second = bot.send_photo.await_args_list
    assert isinstance(first.kwargs["photo"], bytes)
    assert second.kwargs["photo"] == "AgACAgIAAxkDAAI"


def test_daily_card_uses_the_library_face():
    """The daily prompt is a Library item, so it must ride the Library card,
    not the blank framed default the deck falls back to."""
    from vechnost_bot import daily_card

    assert Path(daily_card._BACKGROUND).name == "library.png"
    assert Path(daily_card._BACKGROUND).exists()
