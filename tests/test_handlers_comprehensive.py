"""Comprehensive tests for message handlers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ContextTypes

from vechnost_bot.handlers import (
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
        update.message.text = "/start"
        # The handlers read `effective_user` / `effective_chat`, not
        # `message.from_user`: in a group the two are the same object, but
        # a mock only answers the attribute that is actually asked for.
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.username = "testuser"
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
            mock_context.args = []

            await start_command(mock_update, mock_context)

            # The id only: the handle is a person's public name and stays
            # out of the error tracker.
            mock_set_context.assert_called_once_with(12345)
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
        with patch('vechnost_bot.handlers.get_session') as mock_get_session:
            mock_get_session.return_value = SessionState(language=Language.RUSSIAN)
            mock_update.message.reply_text = AsyncMock()

            await reset_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        # /reset asks before it erases; the two answers are the whole point.
        keyboard = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        assert [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ] == ["reset_confirm", "reset_cancel"]


class TestCallbackHandlers:
    """Test callback query handlers."""

    @pytest.fixture
    def mock_update(self):
        """An update carrying a callback query, as PTB delivers it.

        `handle_callback_query` is registered on the application and is handed
        an Update, not a bare query - the previous version of these tests
        passed the query itself, so the handler read `update.callback_query`
        off a MagicMock and every assertion below it was vacuous.
        """
        update = MagicMock(spec=Update)
        query = MagicMock(spec=CallbackQuery)
        query.message = MagicMock(spec=Message)
        query.message.chat = MagicMock(spec=Chat)
        query.message.chat.id = 12345
        query.data = "test_callback"
        query.answer = AsyncMock()
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
    async def test_handle_callback_query_success(self, mock_update, mock_context):
        """The query is acknowledged, then handed to the registry."""
        with patch(
            'vechnost_bot.callback_handlers.callback_registry'
        ) as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            await handle_callback_query(mock_update, mock_context)

        mock_update.callback_query.answer.assert_awaited_once()
        mock_registry.handle_callback.assert_awaited_once_with(
            mock_update.callback_query, "test_callback"
        )

    @pytest.mark.asyncio
    async def test_handle_callback_query_answers_before_dispatching(
        self, mock_update, mock_context
    ):
        """Telegram spins the button until it is answered.

        So the acknowledgement has to come first: a registry call that takes
        a second to render a card must not leave the player watching a
        spinner, and one that raises must not leave it spinning forever.
        """
        with patch(
            'vechnost_bot.callback_handlers.callback_registry'
        ) as mock_registry:
            mock_registry.handle_callback = AsyncMock(
                side_effect=Exception("Test error")
            )

            with pytest.raises(Exception, match="Test error"):
                await handle_callback_query(mock_update, mock_context)

        mock_update.callback_query.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_callback_query_without_a_message_is_dropped(self, mock_context):
        """A query on a message Telegram has since forgotten has no chat id."""
        update = MagicMock(spec=Update)
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.message = None

        with patch(
            'vechnost_bot.callback_handlers.callback_registry'
        ) as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            await handle_callback_query(update, mock_context)

        mock_registry.handle_callback.assert_not_awaited()


# NSFW and Reset handlers are now in callback_handlers.py


class TestStartCommandLogo:
    """The brand logo `/start` opens with.

    It used to be drawn at runtime by `logo_generator.py`; that module was
    dead - nothing called it but a re-export that existed for a test - and
    `/start` reads a committed PNG instead. What matters now is that a
    missing or unreadable file cannot take `/start` down with it.
    """

    @pytest.fixture
    def mock_update(self):
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.reply_text = AsyncMock()
        update.message.reply_photo = AsyncMock()
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.username = "testuser"
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.id = 12345
        return update

    @pytest.fixture
    def mock_context(self):
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.args = []
        return context

    def test_the_logo_file_is_committed(self):
        assert Path("assets/images/vechnost_logo.png").is_file()

    @pytest.mark.asyncio
    async def test_start_survives_a_missing_logo(self, mock_update, mock_context):
        """No logo is a degraded greeting, never a dead /start."""
        with patch(
            'builtins.open', side_effect=FileNotFoundError("no logo here")
        ):
            await start_command(mock_update, mock_context)

        mock_update.message.reply_photo.assert_not_called()
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_greeting_is_a_message_of_its_own(
        self, mock_update, mock_context
    ):
        """Telegram caps a photo caption at 1024 characters.

        The greeting is longer than that, so it cannot ride along with the
        logo as a caption - it has to be its own message.
        """
        await start_command(mock_update, mock_context)

        mock_update.message.reply_photo.assert_called_once()
        assert "caption" not in mock_update.message.reply_photo.call_args.kwargs
        text = mock_update.message.reply_text.call_args.args[0]
        assert len(text) > 1024
