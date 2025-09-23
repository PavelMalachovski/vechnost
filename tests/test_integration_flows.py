"""Integration tests for complete user flows."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from telegram import Update, Message, Chat, User, CallbackQuery

from vechnost_bot.handlers import start_command, handle_callback_query
from vechnost_bot.callback_handlers import CallbackHandlerRegistry
from vechnost_bot.models import SessionState, Theme, Language, ContentType
from vechnost_bot.storage import get_session, reset_session


class TestCompleteUserFlows:
    """Test complete user interaction flows."""

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
        context = MagicMock()
        context.bot = MagicMock()
        return context

    @pytest.fixture
    def mock_callback_query(self):
        """Create a mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.message = MagicMock(spec=Message)
        query.message.chat = MagicMock(spec=Chat)
        query.message.chat.id = 12345
        query.edit_message_text = AsyncMock()
        query.answer = AsyncMock()
        return query

    def setup_method(self):
        """Clear sessions before each test."""
        reset_session(12345)

    @pytest.mark.asyncio
    async def test_complete_acquaintance_flow(self, mock_update, mock_context, mock_callback_query):
        """Test complete Acquaintance theme flow."""
        # Step 1: Start command
        with patch('vechnost_bot.handlers.get_language_selection_keyboard') as mock_keyboard, \
             patch('vechnost_bot.handlers.detect_language_from_text') as mock_detect, \
             patch('vechnost_bot.handlers.open') as mock_open, \
             patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

            mock_detect.return_value = Language.ENGLISH
            mock_keyboard.return_value = MagicMock()
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_update.message.reply_photo = AsyncMock()

            await start_command(mock_update, mock_context)

            # Verify session was created
            session = get_session(12345)
            assert isinstance(session, SessionState)

        # Step 2: Language selection
        mock_callback_query.data = "lang_en"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "lang_en"
            )

        # Step 3: Theme selection
        mock_callback_query.data = "theme_Acquaintance"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "theme_Acquaintance"
            )

        # Step 4: Level selection
        mock_callback_query.data = "level_1"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "level_1"
            )

        # Step 5: Calendar selection
        mock_callback_query.data = "cal:Acquaintance:1:q:0"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "cal:Acquaintance:1:q:0"
            )

        # Step 6: Question navigation
        mock_callback_query.data = "nav:Acquaintance:1:1"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "nav:Acquaintance:1:1"
            )

    @pytest.mark.asyncio
    async def test_complete_sex_theme_flow(self, mock_update, mock_context, mock_callback_query):
        """Test complete Sex theme flow with NSFW confirmation."""
        # Step 1: Start command
        with patch('vechnost_bot.handlers.get_language_selection_keyboard') as mock_keyboard, \
             patch('vechnost_bot.handlers.detect_language_from_text') as mock_detect, \
             patch('vechnost_bot.handlers.open') as mock_open, \
             patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

            mock_detect.return_value = Language.ENGLISH
            mock_keyboard.return_value = MagicMock()
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_update.message.reply_photo = AsyncMock()

            await start_command(mock_update, mock_context)

        # Step 2: Language selection
        mock_callback_query.data = "lang_en"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 3: Sex theme selection
        mock_callback_query.data = "theme_Sex"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 4: NSFW confirmation
        mock_callback_query.data = "nsfw_confirm"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 5: Calendar selection (questions)
        mock_callback_query.data = "cal:sex:0:q:0"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 6: Toggle to tasks
        mock_callback_query.data = "toggle:sex:0:t"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 7: Calendar selection (tasks)
        mock_callback_query.data = "cal:sex:0:t:0"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_complete_reset_flow(self, mock_update, mock_context, mock_callback_query):
        """Test complete reset flow."""
        # Step 1: Start command
        with patch('vechnost_bot.handlers.get_language_selection_keyboard') as mock_keyboard, \
             patch('vechnost_bot.handlers.detect_language_from_text') as mock_detect, \
             patch('vechnost_bot.handlers.open') as mock_open, \
             patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

            mock_detect.return_value = Language.ENGLISH
            mock_keyboard.return_value = MagicMock()
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_update.message.reply_photo = AsyncMock()

            await start_command(mock_update, mock_context)

        # Step 2: Language selection
        mock_callback_query.data = "lang_en"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 3: Reset request
        mock_callback_query.data = "reset_game"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 4: Reset confirmation
        mock_callback_query.data = "reset_confirm"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_complete_navigation_flow(self, mock_update, mock_context, mock_callback_query):
        """Test complete navigation flow with back buttons."""
        # Step 1: Start command
        with patch('vechnost_bot.handlers.get_language_selection_keyboard') as mock_keyboard, \
             patch('vechnost_bot.handlers.detect_language_from_text') as mock_detect, \
             patch('vechnost_bot.handlers.open') as mock_open, \
             patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

            mock_detect.return_value = Language.ENGLISH
            mock_keyboard.return_value = MagicMock()
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_update.message.reply_photo = AsyncMock()

            await start_command(mock_update, mock_context)

        # Step 2: Language selection
        mock_callback_query.data = "lang_en"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 3: Theme selection
        mock_callback_query.data = "theme_Acquaintance"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 4: Level selection
        mock_callback_query.data = "level_1"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 5: Calendar selection
        mock_callback_query.data = "cal:Acquaintance:1:q:0"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 6: Back to calendar
        mock_callback_query.data = "back:calendar"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Step 7: Back to themes
        mock_callback_query.data = "back:themes"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_error_handling_flow(self, mock_update, mock_context, mock_callback_query):
        """Test error handling in user flows."""
        # Step 1: Start command
        with patch('vechnost_bot.handlers.get_language_selection_keyboard') as mock_keyboard, \
             patch('vechnost_bot.handlers.detect_language_from_text') as mock_detect, \
             patch('vechnost_bot.handlers.open') as mock_open, \
             patch('vechnost_bot.handlers.set_user_context') as mock_set_context:

            mock_detect.return_value = Language.ENGLISH
            mock_keyboard.return_value = MagicMock()
            mock_open.return_value.__enter__.return_value = MagicMock()
            mock_update.message.reply_photo = AsyncMock()

            await start_command(mock_update, mock_context)

        # Step 2: Invalid callback data
        mock_callback_query.data = "invalid_callback_data"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "invalid_callback_data"
            )

        # Step 3: Unknown callback action
        mock_callback_query.data = "unknown_action"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

            mock_registry.handle_callback.assert_called_once_with(
                mock_callback_query, "unknown_action"
            )

    @pytest.mark.asyncio
    async def test_multilingual_flow(self, mock_update, mock_context, mock_callback_query):
        """Test multilingual user flow."""
        # Test Russian flow
        mock_callback_query.data = "lang_ru"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Test Czech flow
        mock_callback_query.data = "lang_cs"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)

        # Test English flow
        mock_callback_query.data = "lang_en"
        with patch('vechnost_bot.callback_handlers.callback_registry') as mock_registry:
            mock_registry.handle_callback = AsyncMock()

            mock_update.callback_query = mock_callback_query
            await handle_callback_query(mock_update, mock_context)
