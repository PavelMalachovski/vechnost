"""Comprehensive tests for message handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ContextTypes

from vechnost_bot.handlers import (
    generate_welcome_image_with_logo,
    handle_callback_query,
    help_command,
    reset_command,
    start_command,
)
from vechnost_bot.models import Language, SessionState


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
        # The command handlers read update.effective_user, which on a real
        # Update is derived rather than the message's own from_user; on a
        # MagicMock it has to be given explicitly or every field comes back
        # as another MagicMock.
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.username = "testuser"
        update.effective_user.first_name = "Test"
        update.effective_user.last_name = None
        update.effective_user.language_code = "ru"
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.id = 12345
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
             patch('vechnost_bot.handlers.get_reset_confirmation_keyboard') as mock_keyboard:

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
        """An Update carrying a callback query, which is what the handler takes."""
        query = MagicMock(spec=CallbackQuery)
        query.message = MagicMock(spec=Message)
        query.message.chat = MagicMock(spec=Chat)
        query.message.chat.id = 12345
        query.data = "test_callback"
        query.answer = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = query
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock context object."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_handle_callback_query_success(self, mock_callback_query, mock_context):
        """The data is handed to the registry, whole and unparsed."""
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            await handle_callback_query(mock_callback_query, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query.callback_query, "test_callback"
            )

    @pytest.mark.asyncio
    async def test_the_query_is_answered_before_it_is_handled(self, mock_callback_query, mock_context):
        """Telegram spins the button until the query is answered.

        So it is answered first, before anything that can fail — a handler
        that raises must not leave the user looking at a spinner.
        """
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock(side_effect=Exception("Test error"))

            with pytest.raises(Exception, match="Test error"):
                await handle_callback_query(mock_callback_query, mock_context)

            mock_callback_query.callback_query.answer.assert_called_once()


# NSFW and Reset handlers are now in callback_handlers.py


class TestUtilityFunctions:
    """Test utility functions."""

    def test_generate_welcome_image_with_logo(self):
        """The welcome image is drawn for real: text first, language second."""
        result = generate_welcome_image_with_logo("Добро пожаловать", "ru")

        assert result is not None
        assert result.getvalue(), "an empty image is not an image"
