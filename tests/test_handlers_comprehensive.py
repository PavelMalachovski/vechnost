"""Comprehensive tests for message handlers."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from telegram import Update, Message, Chat, User, CallbackQuery
from telegram.ext import ContextTypes

from vechnost_bot.handlers import (
    start_command,
    help_command,
    reset_command,
    handle_callback_query,
    generate_welcome_image_with_logo
)
from vechnost_bot.models import SessionState, Theme, Language
from vechnost_bot.i18n import get_text


class TestCommandHandlers:
    """Test command handlers."""

    @pytest.fixture
    def mock_update(self):
        """Create a mock update object."""
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.chat = MagicMock(spec=Chat)
        update.message.chat.id = 12345
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 12345
        update.message.from_user.username = "testuser"
        update.message.text = "/start"
        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock context object."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_start_command_success(self, mock_update, mock_context):
        """Test successful start command."""
        with patch('vechnost_bot.handlers.welcome_screen') as mock_welcome, \
             patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

            keyboard = MagicMock()
            mock_welcome.return_value = ("добро пожаловать", keyboard)
            mock_update.message.reply_text = AsyncMock()
            mock_update.message.reply_photo = AsyncMock()

            await start_command(mock_update, mock_context)

            mock_set_context.assert_called_once_with(12345, "testuser")
            # brand logo first, as its own message, then the greeting
            mock_update.message.reply_photo.assert_called_once()
            mock_update.message.reply_text.assert_called_once_with(
                "добро пожаловать", reply_markup=keyboard, parse_mode="HTML"
            )

    @pytest.mark.asyncio
    async def test_start_command_no_message(self, mock_context):
        """Test start command with no message."""
        update = MagicMock(spec=Update)
        update.message = None

        # Should return early without error
        await start_command(update, mock_context)

    @pytest.mark.asyncio
    async def test_help_command(self, mock_update, mock_context):
        """Test help command."""
        mock_update.message.reply_text = AsyncMock()

        await help_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_command(self, mock_update, mock_context):
        """Test reset command."""
        with patch('vechnost_bot.handlers.get_session') as mock_get_session, \
             patch('vechnost_bot.handlers.get_reset_keyboard') as mock_keyboard:

            mock_session = MagicMock(spec=SessionState)
            mock_session.language = Language.RUSSIAN
            mock_get_session.return_value = mock_session
            mock_keyboard.return_value = MagicMock()
            mock_update.message.reply_text = AsyncMock()

            await reset_command(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()


class TestCallbackHandlers:
    """Test callback query handlers."""

    @pytest.fixture
    def mock_callback_query(self):
        """Create a mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.message = MagicMock(spec=Message)
        query.message.chat = MagicMock(spec=Chat)
        query.message.chat.id = 12345
        query.data = "test_callback"
        return query

    @pytest.fixture
    def mock_context(self):
        """Create a mock context object."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_handle_callback_query_success(self, mock_callback_query, mock_context):
        """Test successful callback query handling."""
        with patch('vechnost_bot.handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            await handle_callback_query(mock_callback_query, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "test_callback"
            )

    @pytest.mark.asyncio
    async def test_handle_callback_query_exception(self, mock_callback_query, mock_context):
        """Test callback query handling with exception."""
        with patch('vechnost_bot.handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback.side_effect = Exception("Test error")
            mock_callback_query.answer = AsyncMock()

            await handle_callback_query(mock_callback_query, mock_context)

            mock_callback_query.answer.assert_called_once()


# NSFW and Reset handlers are now in callback_handlers.py


class TestUtilityFunctions:
    """Test utility functions."""

    @patch('vechnost_bot.handlers.generate_vechnost_logo')
    def test_generate_welcome_image_with_logo(self, mock_generate_logo):
        """Test welcome image generation."""
        mock_generate_logo.return_value = MagicMock()

        result = generate_welcome_image_with_logo(Language.RUSSIAN)

        mock_generate_logo.assert_called_once()
        assert result is not None
