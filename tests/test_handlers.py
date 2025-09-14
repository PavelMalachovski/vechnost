"""Tests for bot handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vechnost_bot.handlers import handle_callback_query, start_command
from vechnost_bot.models import Theme


class TestHandlers:
    """Test bot handlers functionality."""

    @pytest.mark.asyncio
    async def test_start_command(self):
        """Test start command handler."""
        # Mock update and context
        update = MagicMock()
        update.message = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 12345
        context = MagicMock()

        # Mock reply_text
        update.message.reply_text = AsyncMock()

        # Call the handler
        await start_command(update, context)

        # Verify reply_text was called
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Check that reply_markup is present
        assert "reply_markup" in kwargs
        assert kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_callback_query_theme_selection(self):
        """Test callback query for theme selection."""
        # Mock update and context
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "theme_Acquaintance"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message = MagicMock()
        update.callback_query.message.chat = MagicMock()
        update.callback_query.message.chat.id = 12345
        context = MagicMock()

        # Call the handler
        await handle_callback_query(update, context)

        # Verify callback was answered
        update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_query_invalid_data(self):
        """Test callback query with invalid data."""
        # Mock update and context
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "invalid_data"
        update.callback_query.answer = AsyncMock()
        update.callback_query.message = MagicMock()
        update.callback_query.message.chat = MagicMock()
        update.callback_query.message.chat.id = 12345
        context = MagicMock()

        # Call the handler
        await handle_callback_query(update, context)

        # Verify callback was answered
        update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_query_no_data(self):
        """Test callback query with no data."""
        # Mock update and context
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = None
        update.callback_query.answer = AsyncMock()
        update.callback_query.message = MagicMock()
        update.callback_query.message.chat = MagicMock()
        update.callback_query.message.chat.id = 12345
        context = MagicMock()

        # Call the handler
        await handle_callback_query(update, context)

        # Verify callback was answered
        update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_query_no_query(self):
        """Test callback query with no query object."""
        # Mock update and context
        update = MagicMock()
        update.callback_query = None
        context = MagicMock()

        # Call the handler (should return early)
        await handle_callback_query(update, context)

        # Should not raise any exceptions
