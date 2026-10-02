"""A card reaches the chat as the card, whatever message it replaces.

Two ways this used to go wrong, both on the path a tap takes when Telegram
refuses to edit the message in place (it was deleted, it is too old, the
network hiccupped):

- The fallback photo was an empty file. The rendered JPEG sat in a
  `BytesIO`, `InputMediaPhoto` read it to the end while building the edit,
  and the fallback `reply_photo` then sent what was left: zero bytes, which
  Telegram refuses, so the player got an error or nothing.
- «Вопрос недоступен.» was typed into the handler and sent with
  `edit_message_text`, which Telegram refuses on a photo - and every card is
  a photo - so the player read «Неизвестная команда» instead.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from vechnost_bot.callback_handlers import CallbackHandlerRegistry
from vechnost_bot.i18n import get_text


def _query(*, on_a_photo: bool) -> MagicMock:
    """A tap under a card (a photo, sent protected) or under a text message."""
    query = MagicMock()
    query.from_user.id = 7
    query.message.chat.id = 7
    query.message.photo = (MagicMock(),) if on_a_photo else ()
    query.message.has_protected_content = True if on_a_photo else None
    query.message.reply_photo = AsyncMock()
    query.message.delete = AsyncMock()
    query.message.reply_text = AsyncMock()
    query.edit_message_media = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def _payload(photo: object) -> bytes:
    """What would go over the wire: bytes as given, a file as what is left."""
    if isinstance(photo, bytes):
        return photo
    return photo.read()  # type: ignore[attr-defined]


@pytest.mark.parametrize("data", ["q:acq:1:0:q", "nav:acq:1:1:q"])
async def test_the_fallback_photo_is_the_card_not_an_empty_file(data):
    query = _query(on_a_photo=True)
    query.edit_message_media.side_effect = BadRequest("Message to edit not found")

    await CallbackHandlerRegistry().handle_callback(query, data)

    query.message.reply_photo.assert_awaited_once()
    payload = _payload(query.message.reply_photo.await_args.kwargs["photo"])
    assert payload.startswith(b"\xff\xd8"), "the JPEG itself, not a spent BytesIO"
    assert query.message.reply_photo.await_args.kwargs["protect_content"] is True
    query.message.reply_text.assert_not_awaited()


@pytest.mark.parametrize("data", ["q:acq:1:9999:q", "nav:acq:1:9999:q"])
async def test_a_card_that_is_not_there_says_so_under_a_photo(data):
    query = _query(on_a_photo=True)
    query.edit_message_text.side_effect = BadRequest("There is no text in the message to edit")

    await CallbackHandlerRegistry().handle_callback(query, data)

    query.message.reply_text.assert_awaited_once()
    assert query.message.reply_text.await_args.args[0] == get_text("errors.question_unavailable")


async def test_a_card_that_is_not_there_is_said_in_place_on_a_text_message():
    query = _query(on_a_photo=False)

    await CallbackHandlerRegistry().handle_callback(query, "q:acq:1:9999:q")

    query.edit_message_text.assert_awaited_once()
    assert query.edit_message_text.await_args.args[0] == get_text("errors.question_unavailable")
    # Not a dead end: the message offers the decks again.
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    targets = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert any(target.startswith("theme_") for target in targets)
