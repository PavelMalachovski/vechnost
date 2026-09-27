"""Tests for storage module."""

from unittest.mock import AsyncMock, patch

import pytest

from vechnost_bot.models import Language, SessionState
from vechnost_bot.storage import delete_session, get_session


class TestStorage:
    """Test storage functionality."""

    @pytest.mark.asyncio
    async def test_get_session_new(self):
        """Test getting a new session."""
        chat_id = 12345

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.get_session.return_value = None
            mock_storage.save_session = AsyncMock()
            mock_get_storage.return_value = mock_storage

            session = await get_session(chat_id)

            assert isinstance(session, SessionState)
            assert session.language == Language.RUSSIAN
            mock_storage.save_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_existing(self):
        """Test getting an existing session."""
        chat_id = 12345
        existing_session = SessionState(chat_id=chat_id, language=Language.RUSSIAN)

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.get_session.return_value = existing_session
            mock_get_storage.return_value = mock_storage

            session = await get_session(chat_id)

            assert session is existing_session
            assert session.language == Language.RUSSIAN

    @pytest.mark.asyncio
    async def test_delete_session_existing(self):
        """Test deleting an existing session."""
        chat_id = 12345

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.delete_session = AsyncMock()
            mock_get_storage.return_value = mock_storage

            await delete_session(chat_id)

            mock_storage.delete_session.assert_called_once_with(chat_id)

    @pytest.mark.asyncio
    async def test_delete_session_non_existing(self):
        """Test deleting a non-existing session."""
        chat_id = 12345

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.delete_session = AsyncMock()
            mock_get_storage.return_value = mock_storage

            # Should not raise an error
            await delete_session(chat_id)

            mock_storage.delete_session.assert_called_once_with(chat_id)


class _SerializingStore:
    """Hands out a fresh copy on every read, the way Redis does.

    The in-memory store returned the very object it was given, so two reads
    of one chat were one object and a change made through either showed up
    in both. Anything that serializes breaks that, and code that relied on
    it only works in memory.
    """

    def __init__(self) -> None:
        self.rows: dict[int, str] = {}

    async def get_session(self, chat_id: int) -> SessionState | None:
        raw = self.rows.get(chat_id)
        return SessionState.model_validate_json(raw) if raw is not None else None

    async def save_session(self, chat_id: int, session: SessionState, ttl=None) -> None:
        self.rows[chat_id] = session.model_dump_json()

    async def delete_session(self, chat_id: int) -> None:
        self.rows.pop(chat_id, None)


async def test_reset_sticks_when_the_store_serializes_the_session():
    """«Сбросить игру» must reset what is saved, not a copy of it.

    The registry reads the session, runs the handler and saves the session
    back. The reset handler used to reset a *second* copy through
    `storage.reset_session` and save that, after which the registry saved
    its own, untouched copy over it - so with Redis behind the bot the game
    announced a reset and kept the theme, the level and the 18+ consent.
    """
    from unittest.mock import MagicMock

    from vechnost_bot import hybrid_storage
    from vechnost_bot.callback_handlers import CallbackHandlerRegistry
    from vechnost_bot.models import Theme

    store = _SerializingStore()
    chat_id = 4242
    await store.save_session(chat_id, SessionState(
        theme=Theme.SEX, level=2, is_nsfw_confirmed=True,
    ))

    query = MagicMock()
    query.message.chat.id = chat_id
    query.message.photo = ()
    query.edit_message_text = AsyncMock()

    with patch.object(hybrid_storage, "hybrid_storage", store):
        await CallbackHandlerRegistry().handle_callback(query, "reset_confirm")

    saved = await store.get_session(chat_id)
    assert saved is not None
    assert saved.theme is None
    assert saved.level is None
    assert saved.is_nsfw_confirmed is False
