"""Tests for storage module."""

import pytest
from unittest.mock import AsyncMock, patch
from vechnost_bot.models import SessionState, Language
from vechnost_bot.storage import delete_session, get_session, reset_session


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
        existing_session = SessionState(chat_id=chat_id, language=Language.ENGLISH)

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.get_session.return_value = existing_session
            mock_get_storage.return_value = mock_storage

            session = await get_session(chat_id)

            assert session is existing_session
            assert session.language == Language.ENGLISH

    @pytest.mark.asyncio
    async def test_reset_session_existing(self):
        """Test resetting an existing session."""
        chat_id = 12345
        existing_session = SessionState(chat_id=chat_id, language=Language.ENGLISH)

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.get_session.return_value = existing_session
            mock_storage.save_session = AsyncMock()
            mock_get_storage.return_value = mock_storage

            await reset_session(chat_id)

            assert existing_session.language == Language.RUSSIAN
            mock_storage.save_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_session_new(self):
        """Test resetting a non-existing session."""
        chat_id = 12345

        with patch('vechnost_bot.storage.get_redis_storage') as mock_get_storage:
            mock_storage = AsyncMock()
            mock_storage.get_session.return_value = None
            mock_storage.save_session = AsyncMock()
            mock_get_storage.return_value = mock_storage

            await reset_session(chat_id)

            mock_storage.save_session.assert_called_once()

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
