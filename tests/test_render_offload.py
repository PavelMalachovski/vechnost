"""A card is composited once, and never on the event loop.

The renderer used to run Pillow inline inside an `async def`: ~25 ms per
card (145 ms cold), during which the process served nobody else. Rendering
now runs in a worker thread and the result is memoised per card, so a
repeat costs nothing at all. The web process no longer renders cards at
all (the share button and its `/api/card` are gone); the bot does, for
every card it sends.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot import renderer
from vechnost_bot.callback_handlers import NavigationHandler
from vechnost_bot.callback_models import NavigationCallbackData
from vechnost_bot.models import Language, SessionState


def test_the_same_card_is_rendered_once():
    renderer.render_card_bytes.cache_clear()
    bg = renderer.get_background_path("acq", 1, "q")
    first = renderer.render_card_bytes("Вопрос", bg, "Знакомство · 1/30", "VECHNOST")
    second = renderer.render_card_bytes("Вопрос", bg, "Знакомство · 1/30", "VECHNOST")
    assert first == second
    assert renderer.render_card_bytes.cache_info().hits == 1
    assert isinstance(first, bytes), "bytes, so a cached value cannot be consumed"


async def test_the_bot_renders_a_card_off_the_event_loop():
    """The fake renderer asserts there is no running loop in its thread."""
    seen = {}

    def fake_render(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return b"\xff\xd8jpeg"

    query = MagicMock()
    query.from_user.id = 7
    query.message.photo = (MagicMock(),)
    query.message.has_protected_content = True
    query.edit_message_media = AsyncMock()
    with patch("vechnost_bot.callback_handlers.render_card_bytes", fake_render):
        await NavigationHandler().handle(
            query,
            NavigationCallbackData.parse("nav:acq:1:1"),
            SessionState(language=Language.RUSSIAN),
        )

    query.edit_message_media.assert_awaited_once()
    assert seen["on_loop"] is False, "Pillow ran on the event loop"
