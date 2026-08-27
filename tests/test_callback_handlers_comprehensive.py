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
    SimpleActionHandler,
    welcome_screen
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
        session.language = Language.RUSSIAN
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
            mock_session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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
        session.language = Language.RUSSIAN
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

            assert mock_session.language == Language.RUSSIAN
            mock_query.edit_message_text.assert_called_once()


class TestWelcomeScreen:
    """The welcome screen — what `/start` opens on and every 'back' returns to.

    `welcome_screen` is synchronous and needs no fixtures, so unlike the
    handler tests around it these actually execute rather than erroring at
    setup on the suite-wide async-fixture ScopeMismatch.
    """

    @pytest.mark.parametrize("language", list(Language))
    def test_welcome_screen_renders(self, language):
        text, keyboard = welcome_screen(language)

        assert text.strip()
        # get_text() returns the key itself when the key is missing, so a
        # surviving "welcome." in the output means an unresolved key.
        assert "welcome." not in text
        assert "<b>" in text and "</b>" in text, "text is sent with parse_mode=HTML"

    @staticmethod
    def _targets(keyboard):
        return [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]

    @pytest.mark.parametrize("language", list(Language))
    def test_welcome_screen_offers_every_entry_point(self, language):
        """With the optional features configured, every route is on screen.

        The web-app and gift rows are settings-gated, so they are configured
        here explicitly — otherwise this passes vacuously in any environment
        that happens to leave them unset.

        `start_game` is absent on purpose: with the Mini App configured the
        game is played there, so the welcome screen carries no in-chat route
        into a deck. The three web_app rows below are that route.
        """
        configured = MagicMock()
        configured.webapp_url = "https://example.test/app"
        configured.gift_product_id = "gift-1"

        with patch('vechnost_bot.callback_handlers.settings', configured):
            _, keyboard = welcome_screen(language)

        # show_gift is only ever rendered here; losing it strands ShowGiftHandler.
        assert self._targets(keyboard) == ["show_inside", "show_why", "show_gift"]
        web_app_urls = [
            button.web_app.url
            for row in keyboard.inline_keyboard
            for button in row
            if button.web_app
        ]
        # One door into the app, not three. The Library and «69 ступеней»
        # had their own rows here, which put the app's navigation into the
        # chat and meant every new section needed another button beside them.
        assert web_app_urls == ["https://example.test/app"]

    @pytest.mark.parametrize("language", list(Language))
    def test_welcome_screen_without_optional_features(self, language):
        """Unconfigured web app and gift: the core routes still render.

        With no WEBAPP_URL there is no Mini App to send anyone to, so this is
        the one case that still offers the in-chat game. Without it a
        deployment that forgot the variable would greet its users with a
        welcome screen they cannot play from at all.
        """
        bare = MagicMock()
        bare.webapp_url = ""
        bare.gift_product_id = ""
        bare.gift_payment_url = ""

        with patch('vechnost_bot.callback_handlers.settings', bare):
            _, keyboard = welcome_screen(language)

        assert self._targets(keyboard) == ["start_game", "show_inside", "show_why"]

    @pytest.mark.parametrize("data", ["lang_ru", "lang_back", "lang_en", "lang_cs"])
    def test_legacy_language_callbacks_reach_the_welcome_screen(self, data):
        """Buttons already sitting in users' chat histories must still work.

        `lang_ru` is the 'back' target of the inside/why/gift screens;
        `lang_back` came from the deleted chooser; `lang_en`/`lang_cs` from
        before the collapse to Russian. All four fall to the `lang_` prefix
        and land on `LanguageHandler`.
        """
        parsed = CallbackData.parse(data)

        assert parsed.action == CallbackAction.LANGUAGE
        assert isinstance(
            CallbackHandlerRegistry()._handlers[parsed.action], LanguageHandler
        )
        assert Language.coerce(parsed.language_code) is Language.RUSSIAN

    @pytest.mark.parametrize("language", list(Language))
    def test_welcome_screen_buttons_are_labelled(self, language):
        _, keyboard = welcome_screen(language)

        for row in keyboard.inline_keyboard:
            for button in row:
                assert button.text.strip()
                assert "welcome." not in button.text
                assert "gift." not in button.text


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
        session.language = Language.RUSSIAN
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
