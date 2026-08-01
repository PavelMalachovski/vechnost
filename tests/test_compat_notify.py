"""Tests for the compatibility-test completion push.

Sync tests driving the coroutine with `asyncio.run()`, as `test_daily_card.py`
does: the repo's session-scoped `event_loop` fixture in `tests/conftest.py`
makes every `async def` test error out with ScopeMismatch.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.compat_notify import notify_result_ready


def test_both_partners_are_messaged():
    test = MagicMock(
        code="ABC123",
        creator_telegram_user_id=1,
        guest_telegram_user_id=2,
    )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with patch("vechnost_bot.compat_notify._bot", return_value=bot):
        asyncio.run(notify_result_ready(test))

    assert bot.send_message.await_count == 2
    assert {call.kwargs["chat_id"] for call in bot.send_message.await_args_list} == {1, 2}


def test_a_blocked_partner_does_not_stop_the_other():
    from telegram.error import Forbidden

    test = MagicMock(
        code="ABC123",
        creator_telegram_user_id=1,
        guest_telegram_user_id=2,
    )
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[Forbidden("blocked"), None])

    with patch("vechnost_bot.compat_notify._bot", return_value=bot):
        asyncio.run(notify_result_ready(test))

    assert bot.send_message.await_count == 2


def test_no_bot_configured_is_silent():
    test = MagicMock(creator_telegram_user_id=1, guest_telegram_user_id=2)
    with patch("vechnost_bot.compat_notify._bot", return_value=None):
        asyncio.run(notify_result_ready(test))      # must not raise
