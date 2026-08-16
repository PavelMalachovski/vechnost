"""Tests for the compatibility-test completion push.

Sync tests driving the coroutine with `asyncio.run()`, as `test_daily_card.py`
does: the repo's session-scoped `event_loop` fixture in `tests/conftest.py`
makes every `async def` test error out with ScopeMismatch.
"""

import asyncio
import os
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.compat_notify import notify_result_ready
from vechnost_bot.config import settings
from vechnost_bot.i18n import Language, get_text


@contextmanager
def _users(languages):
    """Patch the language lookup's DB access.

    `_languages` imports `get_db` and `UserRepository` inside the function, so
    both are patched where they are defined, not on `compat_notify`.
    `languages` maps telegram user id to the stored language code.
    """
    async def _get(_session, telegram_user_id):
        if telegram_user_id not in languages:
            return None
        return MagicMock(language=languages[telegram_user_id])

    with patch("vechnost_bot.payments.repositories.UserRepository") as repo:
        repo.get_by_telegram_id = AsyncMock(side_effect=_get)
        with patch("vechnost_bot.payments.database.get_db"):
            yield repo


def _send(user_ids, languages=None, bot=None, code="ABC123"):
    """Run the push against a mocked bot and user table. Returns the bot."""
    if bot is None:
        bot = MagicMock()
        bot.send_message = AsyncMock()
    with _users(languages or {}), patch(
        "vechnost_bot.compat_notify._bot", return_value=bot
    ):
        asyncio.run(notify_result_ready(user_ids, code=code))
    return bot


def test_both_partners_are_messaged():
    bot = _send([1, 2])

    assert bot.send_message.await_count == 2
    assert {c.kwargs["chat_id"] for c in bot.send_message.await_args_list} == {1, 2}


def test_a_blocked_partner_does_not_stop_the_other():
    from telegram.error import Forbidden

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[Forbidden("blocked"), None])

    _send([1, 2], bot=bot)

    assert bot.send_message.await_count == 2


def test_no_bot_configured_is_silent():
    with patch("vechnost_bot.compat_notify._bot", return_value=None):
        asyncio.run(notify_result_ready([1, 2], code="ABC123"))  # must not raise


def test_a_test_nobody_joined_sends_nothing():
    """`guest_telegram_user_id` is null until the partner joins."""
    bot = _send([1, None])
    assert bot.send_message.await_count == 1

    bot = _send([None, None])
    assert bot.send_message.await_count == 0


def test_a_partner_with_a_stored_en_or_cs_code_still_gets_messaged():
    """`en`/`cs` are pre-single-language codes left over in the users table;
    `_user_language` coerces both to Russian rather than raising."""
    bot = _send([1, 2], languages={1: "en", 2: "cs"})

    texts = {c.kwargs["chat_id"]: c.kwargs["text"] for c in bot.send_message.await_args_list}
    assert texts[1] == get_text("compat.ready", Language.RUSSIAN)
    assert texts[2] == get_text("compat.ready", Language.RUSSIAN)


def test_an_unknown_user_falls_back_to_russian():
    bot = _send([1, 2], languages={1: "en"})

    texts = {c.kwargs["chat_id"]: c.kwargs["text"] for c in bot.send_message.await_args_list}
    assert texts[2] == get_text("compat.ready", Language.RUSSIAN)


def test_the_button_opens_the_mini_app_not_the_in_app_browser():
    """`url=` lands in Telegram's browser, where initData is empty and the
    Mini App's every /api/compat call 401s. It has to be `web_app=`."""
    with patch.object(settings, "webapp_url", "https://example.com/app"):
        bot = _send([1], languages={1: "en"})

    button = bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.web_app is not None
    assert button.web_app.url == "https://example.com/app"
    assert button.url is None
    assert button.text == get_text("compat.open_button", Language.RUSSIAN)


def test_no_webapp_url_means_no_button():
    with patch.object(settings, "webapp_url", None):
        bot = _send([1])

    assert bot.send_message.await_args.kwargs["reply_markup"] is None
