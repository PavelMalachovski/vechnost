"""Comprehensive tests for callback handlers."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from telegram import Update, Message, Chat, User, CallbackQuery

from vechnost_bot.callback_handlers import (
    CallbackHandlerRegistry,
    ThemeHandler,
    LevelHandler,
    CalendarHandler,
    QuestionHandler,
    NavigationHandler,
    ToggleHandler,
    BackHandler,
    LanguageHandler,
    LanguageConfirmHandler,
    LanguageBackHandler,
    SimpleActionHandler
)
from vechnost_bot.callback_models import (
    CallbackData,
    ThemeCallbackData,
    LevelCallbackData,
    CalendarCallbackData,
    QuestionCallbackData,
    NavigationCallbackData,
    ToggleCallbackData,
    BackCallbackData,
    LanguageCallbackData,
    LanguageConfirmCallbackData,
    LanguageBackCallbackData,
    SimpleCallbackData,
    CallbackAction
)
from vechnost_bot.models import SessionState, Theme, Language, ContentType
from vechnost_bot.i18n import get_text


class TestCallbackHandlerRegistry:
    """Test callback handler registry."""

    @pytest.fixture
    def registry(self):
        """Create callback handler registry."""
        return CallbackHandlerRegistry()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.message = MagicMock(spec=Message)
        query.message.chat = MagicMock(spec=Chat)
        query.message.chat.id = 12345
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS
        return session

    @pytest.mark.asyncio
    async def test_handle_callback_success(self, registry, mock_query, mock_session):
        """Test successful callback handling."""
        with patch('vechnost_bot.callback_handlers.get_session') as mock_get_session, \
             patch('vechnost_bot.callback_handlers.CallbackData.parse') as mock_parse:

            mock_get_session.return_value = mock_session
            mock_callback_data = MagicMock()
            mock_callback_data.action = CallbackAction.THEME
            mock_parse.return_value = mock_callback_data

            await registry.handle_callback(mock_query, "theme_Acquaintance")

            mock_parse.assert_called_once_with("theme_Acquaintance")

    @pytest.mark.asyncio
    async def test_handle_callback_invalid_data(self, registry, mock_query):
        """Test callback handling with invalid data."""
        with patch('vechnost_bot.callback_handlers.get_session') as mock_get_session, \
             patch('vechnost_bot.callback_handlers.CallbackData.parse') as mock_parse, \
             patch('vechnost_bot.callback_handlers.get_text') as mock_get_text:

            mock_session = MagicMock(spec=SessionState)
            mock_session.language = Language.ENGLISH
            mock_get_session.return_value = mock_session
            mock_parse.side_effect = ValueError("Invalid data")
            mock_get_text.return_value = "Unknown command"

            await registry.handle_callback(mock_query, "invalid_data")

            mock_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_no_handler(self, registry, mock_query, mock_session):
        """Test callback handling with no handler."""
        with patch('vechnost_bot.callback_handlers.get_session') as mock_get_session, \
             patch('vechnost_bot.callback_handlers.CallbackData.parse') as mock_parse, \
             patch('vechnost_bot.callback_handlers.get_text') as mock_get_text:

            mock_get_session.return_value = mock_session
            mock_callback_data = MagicMock()
            mock_callback_data.action = "unknown_action"
            mock_parse.return_value = mock_callback_data
            mock_get_text.return_value = "Unknown command"

            await registry.handle_callback(mock_query, "unknown_action")

            mock_query.edit_message_text.assert_called_once()


class TestThemeHandler:
    """Test theme handler."""

    @pytest.fixture
    def handler(self):
        """Create theme handler."""
        return ThemeHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        return session

    @pytest.mark.asyncio
    async def test_handle_acquaintance_theme(self, handler, mock_query, mock_session):
        """Test handling Acquaintance theme."""
        callback_data = ThemeCallbackData(
            action=CallbackAction.THEME,
            raw_data="theme_Acquaintance",
            theme="Acquaintance"
        )

        with patch('vechnost_bot.callback_handlers._show_level_selection') as mock_show_level:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_level.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_sex_theme(self, handler, mock_query, mock_session):
        """Test handling Sex theme."""
        callback_data = ThemeCallbackData(
            action=CallbackAction.THEME,
            raw_data="theme_Sex",
            theme="Sex"
        )

        with patch('vechnost_bot.callback_handlers._show_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_calendar.assert_called_once()


class TestLevelHandler:
    """Test level handler."""

    @pytest.fixture
    def handler(self):
        """Create level handler."""
        return LevelHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.ACQUAINTANCE
        return session

    @pytest.mark.asyncio
    async def test_handle_level_selection(self, handler, mock_query, mock_session):
        """Test level selection handling."""
        callback_data = LevelCallbackData(
            action=CallbackAction.LEVEL,
            raw_data="level_1",
            level=1
        )

        with patch('vechnost_bot.callback_handlers._show_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, mock_session)

            assert mock_session.level == 1
            mock_show_calendar.assert_called_once()


class TestCalendarHandler:
    """Test calendar handler."""

    @pytest.fixture
    def handler(self):
        """Create calendar handler."""
        return CalendarHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS
        return session

    @pytest.mark.asyncio
    async def test_handle_calendar_selection(self, handler, mock_query, mock_session):
        """Test calendar selection handling."""
        callback_data = CalendarCallbackData(
            action=CallbackAction.CALENDAR,
            raw_data="cal:Acquaintance:1:q:0",
            topic="Acquaintance",
            level=1,
            content_type="q",
            page=0
        )

        with patch('vechnost_bot.callback_handlers._show_question') as mock_show_question:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_question.assert_called_once()


class TestQuestionHandler:
    """Test question handler."""

    @pytest.fixture
    def handler(self):
        """Create question handler."""
        return QuestionHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS
        return session

    @pytest.mark.asyncio
    async def test_handle_question_selection(self, handler, mock_query, mock_session):
        """Test question selection handling."""
        callback_data = QuestionCallbackData(
            action=CallbackAction.QUESTION,
            raw_data="q:Acquaintance:1:0",
            topic="Acquaintance",
            level=1,
            question_idx=0
        )

        with patch('vechnost_bot.callback_handlers._show_question') as mock_show_question:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_question.assert_called_once()


class TestNavigationHandler:
    """Test navigation handler."""

    @pytest.fixture
    def handler(self):
        """Create navigation handler."""
        return NavigationHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS
        return session

    @pytest.mark.asyncio
    async def test_handle_navigation(self, handler, mock_query, mock_session):
        """Test navigation handling."""
        callback_data = NavigationCallbackData(
            action=CallbackAction.NAVIGATION,
            raw_data="nav:Acquaintance:1:1",
            topic="Acquaintance",
            level=1,
            question_idx=1
        )

        with patch('vechnost_bot.callback_handlers._show_question') as mock_show_question:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_question.assert_called_once()


class TestToggleHandler:
    """Test toggle handler."""

    @pytest.fixture
    def handler(self):
        """Create toggle handler."""
        return ToggleHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.SEX
        session.level = 0
        session.content_type = ContentType.QUESTIONS
        return session

    @pytest.mark.asyncio
    async def test_handle_toggle_questions_to_tasks(self, handler, mock_query, mock_session):
        """Test toggle from questions to tasks."""
        callback_data = ToggleCallbackData(
            action=CallbackAction.TOGGLE,
            raw_data="toggle:sex:0:t",
            topic="sex",
            page=0,
            category="t"
        )

        with patch('vechnost_bot.callback_handlers._show_sex_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, mock_session)

            assert mock_session.content_type == ContentType.TASKS
            mock_show_calendar.assert_called_once()


class TestBackHandler:
    """Test back handler."""

    @pytest.fixture
    def handler(self):
        """Create back handler."""
        return BackHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        return session

    @pytest.mark.asyncio
    async def test_handle_back_to_themes(self, handler, mock_query, mock_session):
        """Test back to themes."""
        callback_data = BackCallbackData(
            action=CallbackAction.BACK,
            raw_data="back:themes",
            destination="themes"
        )

        with patch('vechnost_bot.callback_handlers._show_theme_selection') as mock_show_theme:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_theme.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_back_to_calendar(self, handler, mock_query, mock_session):
        """Test back to calendar."""
        callback_data = BackCallbackData(
            action=CallbackAction.BACK,
            raw_data="back:calendar",
            destination="calendar"
        )

        with patch('vechnost_bot.callback_handlers._show_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_show_calendar.assert_called_once()


class TestLanguageHandler:
    """Test language handler."""

    @pytest.fixture
    def handler(self):
        """Create language handler."""
        return LanguageHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.RUSSIAN
        return session

    @pytest.mark.asyncio
    async def test_handle_language_selection(self, handler, mock_query, mock_session):
        """Test language selection."""
        callback_data = LanguageCallbackData(
            action=CallbackAction.LANGUAGE,
            raw_data="lang_en",
            language="en"
        )

        with patch('vechnost_bot.callback_handlers.get_text') as mock_get_text, \
             patch('vechnost_bot.callback_handlers.get_theme_keyboard') as mock_keyboard:

            mock_get_text.return_value = "Welcome"
            mock_keyboard.return_value = MagicMock()

            await handler.handle(mock_query, callback_data, mock_session)

            assert mock_session.language == Language.ENGLISH
            mock_query.edit_message_text.assert_called_once()


class TestSimpleActionHandler:
    """Test simple action handler."""

    @pytest.fixture
    def handler(self):
        """Create simple action handler."""
        return SimpleActionHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        query = MagicMock(spec=CallbackQuery)
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock(spec=SessionState)
        session.language = Language.ENGLISH
        return session

    @pytest.mark.asyncio
    async def test_handle_nsfw_confirm(self, handler, mock_query, mock_session):
        """Test NSFW confirmation."""
        callback_data = SimpleCallbackData(
            action=CallbackAction.NSFW_CONFIRM,
            raw_data="nsfw_confirm"
        )

        with patch('vechnost_bot.callback_handlers._handle_nsfw_confirmation') as mock_handle:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_handle.assert_called_once_with(mock_query, mock_session)

    @pytest.mark.asyncio
    async def test_handle_nsfw_deny(self, handler, mock_query, mock_session):
        """Test NSFW denial."""
        callback_data = SimpleCallbackData(
            action=CallbackAction.NSFW_DENY,
            raw_data="nsfw_deny"
        )

        with patch('vechnost_bot.callback_handlers._handle_nsfw_denial') as mock_handle:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_handle.assert_called_once_with(mock_query, mock_session)

    @pytest.mark.asyncio
    async def test_handle_reset_game(self, handler, mock_query, mock_session):
        """Test reset game."""
        callback_data = SimpleCallbackData(
            action=CallbackAction.RESET_GAME,
            raw_data="reset_game"
        )

        with patch('vechnost_bot.callback_handlers._handle_reset_request') as mock_handle:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_handle.assert_called_once_with(mock_query, mock_session)

    @pytest.mark.asyncio
    async def test_handle_reset_confirm(self, handler, mock_query, mock_session):
        """Test reset confirmation."""
        callback_data = SimpleCallbackData(
            action=CallbackAction.RESET_CONFIRM,
            raw_data="reset_confirm"
        )

        with patch('vechnost_bot.callback_handlers._handle_reset_confirmation') as mock_handle:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_handle.assert_called_once_with(mock_query, mock_session)

    @pytest.mark.asyncio
    async def test_handle_reset_cancel(self, handler, mock_query, mock_session):
        """Test reset cancellation."""
        callback_data = SimpleCallbackData(
            action=CallbackAction.RESET_CANCEL,
            raw_data="reset_cancel"
        )

        with patch('vechnost_bot.callback_handlers._handle_reset_cancellation') as mock_handle:
            await handler.handle(mock_query, callback_data, mock_session)

            mock_handle.assert_called_once_with(mock_query, mock_session)

    @pytest.mark.asyncio
    async def test_handle_noop(self, handler, mock_query, mock_session):
        """Test no-op action."""
        callback_data = SimpleCallbackData(
            action=CallbackAction.NOOP,
            raw_data="noop"
        )

        # Should not raise any exceptions
        await handler.handle(mock_query, callback_data, mock_session)
