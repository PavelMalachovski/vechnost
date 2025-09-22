"""Tests for callback handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vechnost_bot.callback_handlers import (
    BackHandler,
    CalendarHandler,
    CallbackHandlerRegistry,
    LevelHandler,
    NavigationHandler,
    QuestionHandler,
    SimpleActionHandler,
    ThemeHandler,
    ToggleHandler,
)
from vechnost_bot.callback_models import (
    BackCallbackData,
    CalendarCallbackData,
    CallbackAction,
    LevelCallbackData,
    NavigationCallbackData,
    QuestionCallbackData,
    SimpleCallbackData,
    ThemeCallbackData,
    ToggleCallbackData,
)
from vechnost_bot.models import ContentType, SessionState, Theme


class TestThemeHandler:
    """Test ThemeHandler."""

    @pytest.fixture
    def handler(self):
        return ThemeHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.reply_text = AsyncMock()
        query.message.delete = AsyncMock()
        return query

    @pytest.fixture
    def session(self):
        return SessionState()

    @pytest.mark.asyncio
    async def test_handle_theme_selection_acquaintance(self, handler, mock_query, session):
        """Test handling acquaintance theme selection."""
        callback_data = ThemeCallbackData(
            raw_data="theme_Acquaintance",
            theme_name="Acquaintance"
        )

        with patch.object(handler, '_show_level_selection') as mock_show_level:
            await handler.handle(mock_query, callback_data, session)

            assert session.theme == Theme.ACQUAINTANCE
            mock_show_level.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_theme_selection_sex(self, handler, mock_query, session):
        """Test handling sex theme selection."""
        callback_data = ThemeCallbackData(
            raw_data="theme_Sex",
            theme_name="Sex"
        )

        with patch('vechnost_bot.callback_handlers.localized_game_data') as mock_game_data:
            mock_game_data.has_nsfw_content.return_value = False

            with patch.object(handler, '_show_calendar') as mock_show_calendar:
                await handler.handle(mock_query, callback_data, session)

                assert session.theme == Theme.SEX
                assert session.content_type == ContentType.QUESTIONS
                mock_show_calendar.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_theme_selection_invalid(self, handler, mock_query, session):
        """Test handling invalid theme selection."""
        callback_data = ThemeCallbackData(
            raw_data="theme_Invalid",
            theme_name="Invalid"
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()


class TestLevelHandler:
    """Test LevelHandler."""

    @pytest.fixture
    def handler(self):
        return LevelHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def session(self):
        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        return session

    @pytest.mark.asyncio
    async def test_handle_level_selection(self, handler, mock_query, session):
        """Test handling level selection."""
        callback_data = LevelCallbackData(
            raw_data="level_2",
            level=2
        )

        with patch.object(handler, '_show_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, session)

            assert session.level == 2
            assert session.content_type == ContentType.QUESTIONS
            mock_show_calendar.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_level_selection_no_theme(self, handler, mock_query, session):
        """Test handling level selection without theme."""
        session.theme = None
        callback_data = LevelCallbackData(
            raw_data="level_2",
            level=2
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()


class TestCalendarHandler:
    """Test CalendarHandler."""

    @pytest.fixture
    def handler(self):
        return CalendarHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def session(self):
        return SessionState()

    @pytest.mark.asyncio
    async def test_handle_calendar_navigation(self, handler, mock_query, session):
        """Test handling calendar navigation."""
        callback_data = CalendarCallbackData(
            raw_data="cal:acq:1:q:0",
            topic="acq",
            level_or_0=1,
            category="q",
            page=0
        )

        with patch.object(handler, '_show_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, session)

            assert session.theme == Theme.ACQUAINTANCE
            assert session.level == 1
            mock_show_calendar.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_calendar_navigation_invalid_theme(self, handler, mock_query, session):
        """Test handling calendar navigation with invalid theme."""
        callback_data = CalendarCallbackData(
            raw_data="cal:invalid:1:q:0",
            topic="invalid",
            level_or_0=1,
            category="q",
            page=0
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()


class TestQuestionHandler:
    """Test QuestionHandler."""

    @pytest.fixture
    def handler(self):
        return QuestionHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        query.edit_message_media = AsyncMock()
        query.message = MagicMock()
        query.message.reply_photo = AsyncMock()
        return query

    @pytest.fixture
    def session(self):
        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS
        return session

    @pytest.mark.asyncio
    async def test_handle_question_selection(self, handler, mock_query, session):
        """Test handling question selection."""
        callback_data = QuestionCallbackData(
            raw_data="q:acq:1:5",
            topic="acq",
            level_or_0=1,
            index=5
        )

        with patch('vechnost_bot.callback_handlers.localized_game_data') as mock_game_data:
            mock_game_data.get_content.return_value = ["q1", "q2", "q3", "q4", "q5", "q6"]

            with patch('vechnost_bot.callback_handlers.get_background_path') as mock_bg_path:
                mock_bg_path.return_value = "test_bg.png"

                with patch('vechnost_bot.callback_handlers.render_card') as mock_render:
                    mock_render.return_value = MagicMock()

                    await handler.handle(mock_query, callback_data, session)

                    assert session.theme == Theme.ACQUAINTANCE
                    assert session.level == 1
                    mock_query.edit_message_media.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_question_selection_invalid_theme(self, handler, mock_query, session):
        """Test handling question selection with invalid theme."""
        callback_data = QuestionCallbackData(
            raw_data="q:invalid:1:5",
            topic="invalid",
            level_or_0=1,
            index=5
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_question_selection_invalid_index(self, handler, mock_query, session):
        """Test handling question selection with invalid index."""
        callback_data = QuestionCallbackData(
            raw_data="q:acq:1:10",
            topic="acq",
            level_or_0=1,
            index=10
        )

        with patch('vechnost_bot.callback_handlers.localized_game_data') as mock_game_data:
            mock_game_data.get_content.return_value = ["q1", "q2", "q3"]

            await handler.handle(mock_query, callback_data, session)

            mock_query.edit_message_text.assert_called_once()


class TestToggleHandler:
    """Test ToggleHandler."""

    @pytest.fixture
    def handler(self):
        return ToggleHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        return query

    @pytest.fixture
    def session(self):
        return SessionState()

    @pytest.mark.asyncio
    async def test_handle_toggle_content(self, handler, mock_query, session):
        """Test handling content toggle."""
        callback_data = ToggleCallbackData(
            raw_data="toggle:sex:q:0",
            topic="sex",
            category="q",
            page=0
        )

        with patch.object(handler, '_show_sex_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, session)

            assert session.theme == Theme.SEX
            assert session.level is None
            assert session.content_type == ContentType.QUESTIONS
            mock_show_calendar.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_toggle_content_invalid_topic(self, handler, mock_query, session):
        """Test handling content toggle with invalid topic."""
        callback_data = ToggleCallbackData(
            raw_data="toggle:invalid:q:0",
            topic="invalid",
            category="q",
            page=0
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()


class TestBackHandler:
    """Test BackHandler."""

    @pytest.fixture
    def handler(self):
        return BackHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.reply_text = AsyncMock()
        query.message.delete = AsyncMock()
        return query

    @pytest.fixture
    def session(self):
        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        return session

    @pytest.mark.asyncio
    async def test_handle_back_to_themes(self, handler, mock_query, session):
        """Test handling back to themes."""
        callback_data = BackCallbackData(
            raw_data="back:themes",
            destination="themes"
        )

        with patch.object(handler, '_show_theme_selection') as mock_show_theme:
            await handler.handle(mock_query, callback_data, session)

            mock_show_theme.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_back_to_levels(self, handler, mock_query, session):
        """Test handling back to levels."""
        callback_data = BackCallbackData(
            raw_data="back:levels",
            destination="levels"
        )

        with patch('vechnost_bot.callback_handlers.localized_game_data') as mock_game_data:
            mock_game_data.get_available_levels.return_value = [1, 2, 3]

            with patch.object(handler, '_show_level_selection') as mock_show_level:
                await handler.handle(mock_query, callback_data, session)

                mock_show_level.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_back_to_calendar(self, handler, mock_query, session):
        """Test handling back to calendar."""
        callback_data = BackCallbackData(
            raw_data="back:calendar",
            destination="calendar"
        )

        with patch.object(handler, '_show_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, session)

            mock_show_calendar.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_back_unknown_destination(self, handler, mock_query, session):
        """Test handling back with unknown destination."""
        callback_data = BackCallbackData(
            raw_data="back:unknown",
            destination="unknown"
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()


class TestSimpleActionHandler:
    """Test SimpleActionHandler."""

    @pytest.fixture
    def handler(self):
        return SimpleActionHandler()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.chat = MagicMock()
        query.message.chat.id = 12345
        return query

    @pytest.fixture
    def session(self):
        return SessionState()

    @pytest.mark.asyncio
    async def test_handle_nsfw_confirm(self, handler, mock_query, session):
        """Test handling NSFW confirmation."""
        callback_data = SimpleCallbackData(
            raw_data="nsfw_confirm",
            action=CallbackAction.NSFW_CONFIRM
        )

        session.theme = Theme.SEX

        with patch.object(handler, '_show_sex_calendar') as mock_show_calendar:
            await handler.handle(mock_query, callback_data, session)

            assert session.is_nsfw_confirmed is True
            assert session.content_type == ContentType.QUESTIONS
            mock_show_calendar.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_nsfw_deny(self, handler, mock_query, session):
        """Test handling NSFW denial."""
        callback_data = SimpleCallbackData(
            raw_data="nsfw_deny",
            action=CallbackAction.NSFW_DENY
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_reset_confirm(self, handler, mock_query, session):
        """Test handling reset confirmation."""
        callback_data = SimpleCallbackData(
            raw_data="reset_confirm",
            action=CallbackAction.RESET_CONFIRM
        )

        with patch('vechnost_bot.callback_handlers.reset_session') as mock_reset:
            await handler.handle(mock_query, callback_data, session)

            mock_reset.assert_called_once_with(12345)
            mock_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_noop(self, handler, mock_query, session):
        """Test handling noop action."""
        callback_data = SimpleCallbackData(
            raw_data="noop",
            action=CallbackAction.NOOP
        )

        await handler.handle(mock_query, callback_data, session)

        # Should not call any methods
        mock_query.edit_message_text.assert_not_called()


class TestCallbackHandlerRegistry:
    """Test CallbackHandlerRegistry."""

    @pytest.fixture
    def registry(self):
        return CallbackHandlerRegistry()

    @pytest.fixture
    def mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.chat = MagicMock()
        query.message.chat.id = 12345
        return query

    @pytest.mark.asyncio
    async def test_handle_callback_theme(self, registry, mock_query):
        """Test handling theme callback through registry."""
        with patch('vechnost_bot.callback_handlers.get_session') as mock_get_session:
            mock_session = SessionState()
            mock_get_session.return_value = mock_session

            with patch.object(registry._handlers[CallbackAction.THEME], 'handle') as mock_handle:
                await registry.handle_callback(mock_query, "theme_Acquaintance")

                mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_invalid_data(self, registry, mock_query):
        """Test handling invalid callback data through registry."""
        await registry.handle_callback(mock_query, "invalid_data")

        mock_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_exception(self, registry, mock_query):
        """Test handling callback with exception through registry."""
        with patch('vechnost_bot.callback_handlers.get_session') as mock_get_session:
            mock_get_session.side_effect = Exception("Test error")

            await registry.handle_callback(mock_query, "theme_Acquaintance")

            # The exception is thrown in get_session, so edit_message_text won't be called
            # because the error handling code also calls get_session which throws an exception
            mock_query.edit_message_text.assert_not_called()
