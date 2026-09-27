"""What a person sees when something goes wrong, or when nobody asked.

Three silences and one wrong answer, all fixed here:

- A command that raised (/start, /help, /about...) went to the global error
  handler, which only logged it: the sender saw nothing at all.
- A button that failed on the database or the network answered
  «Неизвестная команда», which sends people looking for their own mistake.
- Text nobody asked for got no answer, a pasted certificate code included -
  the first thing someone holding a gift card tries.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.error import Conflict, Forbidden, TimedOut

from vechnost_bot import bot as bot_module
from vechnost_bot.callback_handlers import CallbackHandlerRegistry
from vechnost_bot.config import settings
from vechnost_bot.i18n import get_text

from .e2e.fake_telegram import FakeTelegram

CHAT = 777_000_123
_ids = iter(range(1, 1_000_000))


def _message(text: str) -> dict[str, Any]:
    entities = []
    if text.startswith("/"):
        entities = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {
        "update_id": next(_ids),
        "message": {
            "message_id": next(_ids),
            "date": 0,
            "chat": {"id": CHAT, "type": "private", "first_name": "Ann"},
            "from": {"id": CHAT, "is_bot": False, "first_name": "Ann"},
            "text": text,
            "entities": entities,
        },
    }


@pytest.fixture
async def app():
    """The real application, over a fake Bot API that records every call."""
    telegram = FakeTelegram("vechnost_test_bot")
    with patch.object(
        bot_module, "create_bot", lambda: telegram.bot(settings.telegram_bot_token)
    ):
        application = bot_module.create_application()
    await application.initialize()
    try:
        yield application, telegram
    finally:
        await application.shutdown()


async def _say(application, text: str) -> None:
    await application.process_update(Update.de_json(_message(text), application.bot))


# ---------------------------------------------------------------------------
# A failing command is answered
# ---------------------------------------------------------------------------

async def test_a_command_that_fails_gets_a_short_apology(app):
    application, telegram = app
    with patch("vechnost_bot.handlers.get_session", side_effect=RuntimeError("db down")):
        await _say(application, "/help")

    assert telegram.texts_to(CHAT) == [get_text("errors.something_went_wrong")]


async def test_the_apology_carries_no_detail(app):
    application, telegram = app
    with patch("vechnost_bot.handlers.get_session",
               side_effect=RuntimeError("password=hunter2 at db.internal")):
        await _say(application, "/about")

    [said] = telegram.texts_to(CHAT)
    assert "hunter2" not in said and "Traceback" not in said


async def test_an_error_with_no_chat_behind_it_tells_nobody():
    """A failed poll or a scheduled job has nobody to apologise to."""
    context = MagicMock()
    context.error = RuntimeError("job failed")
    context.bot.send_message = AsyncMock()

    await bot_module.on_error(None, context)

    context.bot.send_message.assert_not_awaited()


async def test_a_conflict_between_two_pollers_is_not_a_users_business():
    context = MagicMock()
    context.error = Conflict("terminated by other getUpdates request")
    context.bot.send_message = AsyncMock()
    update = MagicMock(spec=Update)
    update.effective_chat.id = CHAT

    await bot_module.on_error(update, context)

    context.bot.send_message.assert_not_awaited()


@pytest.mark.parametrize("error", [TimedOut("Pool timeout"), RuntimeError("boom")])
async def test_a_transient_error_is_answered_too(error):
    """A pool timeout is exactly the error a player never heard about."""
    context = MagicMock()
    context.error = error
    context.bot.send_message = AsyncMock()
    update = MagicMock(spec=Update)
    update.effective_chat.id = CHAT

    await bot_module.on_error(update, context)

    context.bot.send_message.assert_awaited_once_with(
        chat_id=CHAT, text=get_text("errors.something_went_wrong")
    )


async def test_an_apology_that_cannot_be_delivered_does_not_raise():
    context = MagicMock()
    context.error = RuntimeError("boom")
    context.bot.send_message = AsyncMock(side_effect=Forbidden("bot was blocked"))
    update = MagicMock(spec=Update)
    update.effective_chat.id = CHAT

    await bot_module.on_error(update, context)


# ---------------------------------------------------------------------------
# A button that fails is not an unknown command
# ---------------------------------------------------------------------------

def _query() -> MagicMock:
    query = MagicMock()
    query.message.chat.id = CHAT
    query.message.photo = ()
    query.edit_message_text = AsyncMock()
    return query


async def test_a_button_that_fails_says_so_rather_than_unknown_command():
    query = _query()
    with patch("vechnost_bot.callback_handlers.get_session",
               side_effect=ConnectionError("Redis went away")):
        await CallbackHandlerRegistry().handle_callback(query, "theme_Acquaintance")

    text = query.edit_message_text.await_args.args[0]
    assert text == get_text("errors.callback_failed")
    assert text != get_text("errors.unknown_callback")


async def test_a_handler_failing_on_validation_is_not_an_unknown_command_either():
    """pydantic's ValidationError is a ValueError, and the old `except
    ValueError` around everything filed it under «unknown command»."""
    from pydantic import BaseModel

    class Strict(BaseModel):
        n: int

    query = _query()
    handler = CallbackHandlerRegistry()
    theme_handler = MagicMock()
    theme_handler.handle = AsyncMock(side_effect=lambda *a: Strict(n="x"))
    from vechnost_bot.callback_models import CallbackAction

    handler._handlers[CallbackAction.THEME] = theme_handler
    await handler.handle_callback(query, "theme_Acquaintance")

    assert query.edit_message_text.await_args.args[0] == get_text("errors.callback_failed")


async def test_a_button_the_bot_does_not_know_is_still_unknown():
    query = _query()
    await CallbackHandlerRegistry().handle_callback(query, "no-such-button")

    assert query.edit_message_text.await_args.args[0] == get_text("errors.unknown_callback")


# ---------------------------------------------------------------------------
# Text nobody asked for
# ---------------------------------------------------------------------------

async def test_free_text_gets_a_hint(app):
    application, telegram = app
    await _say(application, "привет, а как тут играть?")

    assert telegram.texts_to(CHAT) == [get_text("hints.free_text")]


@pytest.mark.parametrize("typed", [
    "VECH-AB2C-DE3F",
    "vech-ab2c-de3f",
    "VECHAB2CDE3F",
    "вот мой код: VECH AB2C DE3F, спасибо!",
])
async def test_a_pasted_certificate_code_is_pointed_at_activate(app, typed):
    application, telegram = app
    await _say(application, typed)

    [sent] = telegram.to(CHAT)
    assert sent.text == get_text("hints.certificate", code="VECH-AB2C-DE3F")
    assert sent.params.get("parse_mode") == "HTML"
    assert "<code>/activate VECH-AB2C-DE3F</code>" in sent.text


async def test_the_hint_never_logs_what_was_typed(app, caplog):
    """Ours, at any level. (python-telegram-bot's own DEBUG output echoes
    every API call; production logs at INFO.)"""
    application, _ = app
    caplog.set_level("DEBUG")
    await _say(application, "VECH-AB2C-DE3F")
    ours = [r.getMessage() for r in caplog.records if r.name.startswith("vechnost_bot")]
    assert not any("AB2C" in line for line in ours)


async def test_a_command_is_not_mistaken_for_free_text(app):
    application, telegram = app
    with patch("vechnost_bot.handlers.get_session", AsyncMock()) as session:
        session.return_value.language = "ru"
        await _say(application, "/help")

    texts = telegram.texts_to(CHAT)
    assert get_text("hints.free_text") not in texts


async def test_an_edited_message_is_not_answered(app):
    application, telegram = app
    update = _message("исправленный текст")
    update["edited_message"] = update.pop("message")
    update["edited_message"]["edit_date"] = 1
    await application.process_update(Update.de_json(update, application.bot))

    assert telegram.to(CHAT) == []


async def test_group_chatter_is_left_alone(app):
    application, telegram = app
    update = _message("всем привет")
    update["message"]["chat"] = {"id": -100_500, "type": "supergroup", "title": "g"}
    await application.process_update(Update.de_json(update, application.bot))

    assert telegram.sent == []
