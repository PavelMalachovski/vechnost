"""A card is composited once, and never on the event loop.

`/api/card` used to call Pillow inline inside an `async def`: ~25 ms per
card (145 ms cold), during which the one web process served nobody - not
the webhook, not the games. Rendering now runs in a worker thread and the
result is memoised per card, so a repeat request costs nothing at all.
"""

import asyncio
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from fastapi.testclient import TestClient

import vechnost_bot.payments.database as database
from vechnost_bot import renderer
from vechnost_bot.config import settings
from vechnost_bot.payments import throttle
from vechnost_bot.payments.web import app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "render.db"
    with (
        patch.object(settings, "database_url", f"sqlite:///{db_path}"),
        patch.object(settings, "enable_payment", False),
        patch.object(database, "engine", None),
        patch.object(database, "async_session_maker", None),
        patch.object(database, "_tables_created", False),
    ):
        throttle.reset()
        yield TestClient(app)


def test_the_same_card_is_rendered_once():
    renderer.render_card_bytes.cache_clear()
    bg = renderer.get_background_path("acq", 1, "q")
    first = renderer.render_card_bytes("Вопрос", bg, "Знакомство · 1/30", "VECHNOST")
    second = renderer.render_card_bytes("Вопрос", bg, "Знакомство · 1/30", "VECHNOST")
    assert first == second
    assert renderer.render_card_bytes.cache_info().hits == 1
    assert isinstance(first, bytes), "bytes, so a cached value cannot be consumed"


def test_the_card_endpoint_renders_off_the_event_loop(client):
    """The fake renderer asserts there is no running loop in its thread."""
    seen = {}

    def fake_render(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return b"\xff\xd8jpeg"

    with patch("vechnost_bot.payments.web.render_card_bytes", fake_render):
        response = client.get("/api/card?theme=Acquaintance&level=1&idx=0")

    assert response.status_code == 200
    assert response.content == b"\xff\xd8jpeg"
    assert seen["on_loop"] is False, "Pillow ran on the event loop"
