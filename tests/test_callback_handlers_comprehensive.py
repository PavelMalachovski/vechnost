"""Comprehensive tests for callback handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message

from vechnost_bot.callback_handlers import (
    BackHandler,
    CalendarHandler,
    CallbackHandlerRegistry,
    LanguageHandler,
    LevelHandler,
    NavigationHandler,
    QuestionHandler,
    SimpleActionHandler,
    ThemeHandler,
    ToggleHandler,
    welcome_screen,
)
from vechnost_bot.callback_models import (
    BackCallbackData,
    CalendarCallbackData,
    CallbackAction,
    CallbackData,
    LanguageCallbackData,
    LevelCallbackData,
    NavigationCallbackData,
    QuestionCallbackData,
    SimpleCallbackData,
    ThemeCallbackData,
    ToggleCallbackData,
)
from vechnost_bot.models import ContentType, Language, SessionState, Theme


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
        query.message.photo = ()  # a text message, not a photo card
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


def _make_query():
    """A callback query that records what the handler sent it.

    Not `spec=CallbackQuery`: these handlers reach for `query.message.chat.id`
    and for `reply_photo`, and a spec'd mock of a class whose attributes are
    read-only properties makes those awkward to set up without saying anything
    about the handler under test.
    """
    query = MagicMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_media = AsyncMock()
    query.message = MagicMock()
    query.message.photo = ()  # a text message, not a photo card
    query.message.chat.id = 12345
    query.message.reply_text = AsyncMock()
    query.message.reply_photo = AsyncMock()
    query.message.delete = AsyncMock()
    return query


def _keyboard_of(mock_call):
    """The `reply_markup` of the last call, keyword or positional."""
    assert mock_call.call_args is not None, "nothing was sent"
    keyboard = mock_call.call_args.kwargs.get("reply_markup")
    if keyboard is None and len(mock_call.call_args.args) > 1:
        keyboard = mock_call.call_args.args[1]
    return keyboard


def _callback_targets(keyboard):
    """Every callback_data on a keyboard, in reading order.

    Asserting on these rather than on the name of some private function the
    handler was expected to call: the button a player can press is the part
    that has to keep working, and it survives the handlers being refactored
    into classes, which the previous version of these tests did not.
    """
    assert keyboard is not None, "no keyboard was attached"
    return [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]


class TestThemeHandler:
    """Test theme handler."""

    @pytest.fixture
    def handler(self):
        """Create theme handler."""
        return ThemeHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(language=Language.RUSSIAN)

    @pytest.mark.asyncio
    async def test_handle_acquaintance_theme(self, handler, mock_query, session):
        """A levelled theme opens its level menu."""
        callback_data = ThemeCallbackData(
            action=CallbackAction.THEME,
            raw_data="theme_Acquaintance",
            theme_name="Acquaintance",
        )

        await handler.handle(mock_query, callback_data, session)

        assert session.theme == Theme.ACQUAINTANCE
        levels = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert levels == ["level_1", "level_2", "level_3", "back:themes"]

    @pytest.mark.asyncio
    async def test_handle_sex_theme_asks_for_nsfw_confirmation_first(
        self, handler, mock_query, session
    ):
        """Sex is the one NSFW theme: the warning comes before the cards."""
        callback_data = ThemeCallbackData(
            action=CallbackAction.THEME, raw_data="theme_Sex", theme_name="Sex"
        )

        await handler.handle(mock_query, callback_data, session)

        assert session.theme == Theme.SEX
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert "nsfw_confirm" in targets and "nsfw_deny" in targets

    @pytest.mark.asyncio
    async def test_handle_sex_theme_once_confirmed_opens_the_calendar(
        self, handler, mock_query, session
    ):
        session.is_nsfw_confirmed = True
        callback_data = ThemeCallbackData(
            action=CallbackAction.THEME, raw_data="theme_Sex", theme_name="Sex"
        )

        await handler.handle(mock_query, callback_data, session)

        assert session.content_type == ContentType.QUESTIONS
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("q:sex:") for t in targets)

    @pytest.mark.asyncio
    async def test_handle_unknown_theme(self, handler, mock_query, session):
        """A theme name that is not one of ours is refused, not raised."""
        callback_data = ThemeCallbackData(
            action=CallbackAction.THEME,
            raw_data="theme_Nonsense",
            theme_name="Nonsense",
        )

        await handler.handle(mock_query, callback_data, session)

        assert session.theme is None
        mock_query.edit_message_text.assert_called_once()


class TestLevelHandler:
    """Test level handler."""

    @pytest.fixture
    def handler(self):
        """Create level handler."""
        return LevelHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(language=Language.RUSSIAN, theme=Theme.ACQUAINTANCE)

    @pytest.mark.asyncio
    async def test_handle_level_selection(self, handler, mock_query, session):
        """Picking a level opens that level's calendar."""
        callback_data = LevelCallbackData(
            action=CallbackAction.LEVEL, raw_data="level_1", level=1
        )

        await handler.handle(mock_query, callback_data, session)

        assert session.level == 1
        assert session.content_type == ContentType.QUESTIONS
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("q:acq:1:") for t in targets)

    @pytest.mark.asyncio
    async def test_level_without_a_theme_is_refused(self, handler, mock_query):
        """A stale button from a reset session must not open a calendar."""
        session = SessionState(language=Language.RUSSIAN)
        callback_data = LevelCallbackData(
            action=CallbackAction.LEVEL, raw_data="level_1", level=1
        )

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()
        assert _keyboard_of(mock_query.edit_message_text) is None


class TestCalendarHandler:
    """Test calendar handler."""

    @pytest.fixture
    def handler(self):
        """Create calendar handler."""
        return CalendarHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(language=Language.RUSSIAN)

    @pytest.mark.asyncio
    async def test_handle_calendar_selection(self, handler, mock_query, session):
        """A calendar callback restores theme, level and content type."""
        callback_data = CalendarCallbackData.parse("cal:acq:1:q:0")

        await handler.handle(mock_query, callback_data, session)

        assert session.theme == Theme.ACQUAINTANCE
        assert session.level == 1
        assert session.content_type == ContentType.QUESTIONS
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("q:acq:1:") for t in targets)

    @pytest.mark.asyncio
    async def test_unknown_topic_is_refused(self, handler, mock_query, session):
        callback_data = CalendarCallbackData.parse("cal:nope:1:q:0")

        await handler.handle(mock_query, callback_data, session)

        assert session.theme is None
        mock_query.edit_message_text.assert_called_once()


class TestQuestionHandler:
    """Test question handler."""

    @pytest.fixture
    def handler(self):
        """Create question handler."""
        return QuestionHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(language=Language.RUSSIAN)

    @pytest.mark.asyncio
    async def test_handle_question_selection(self, handler, mock_query, session):
        """The first card is free, and arrives as a rendered photo."""
        callback_data = QuestionCallbackData.parse("q:acq:1:0")

        await handler.handle(mock_query, callback_data, session)

        assert session.theme == Theme.ACQUAINTANCE
        assert session.level == 1
        mock_query.edit_message_media.assert_called_once()
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_media))
        assert "nav:acq:1:1:q" in targets

    @pytest.mark.asyncio
    async def test_an_index_past_the_deck_is_refused(
        self, handler, mock_query, session
    ):
        callback_data = QuestionCallbackData.parse("q:acq:1:9999")

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_media.assert_not_called()
        mock_query.edit_message_text.assert_called_once()


class TestNavigationHandler:
    """Test navigation handler."""

    @pytest.fixture
    def handler(self):
        """Create navigation handler."""
        return NavigationHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(language=Language.RUSSIAN)

    @pytest.mark.asyncio
    async def test_handle_navigation(self, handler, mock_query, session):
        """Stepping to the next card keeps the deck and moves the index."""
        callback_data = NavigationCallbackData.parse("nav:acq:1:1")

        await handler.handle(mock_query, callback_data, session)

        assert session.theme == Theme.ACQUAINTANCE
        assert session.level == 1
        mock_query.edit_message_media.assert_called_once()
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_media))
        assert "nav:acq:1:0:q" in targets and "nav:acq:1:2:q" in targets


class TestToggleHandler:
    """Test toggle handler."""

    @pytest.fixture
    def handler(self):
        """Create toggle handler."""
        return ToggleHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(
            language=Language.RUSSIAN,
            theme=Theme.SEX,
            content_type=ContentType.QUESTIONS,
        )

    @pytest.mark.asyncio
    async def test_handle_toggle_questions_to_tasks(
        self, handler, mock_query, session
    ):
        """The toggle switches the deck and redraws the calendar on it."""
        callback_data = ToggleCallbackData.parse("toggle:sex:0:t")

        await handler.handle(mock_query, callback_data, session)

        assert session.content_type == ContentType.TASKS
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("q:sex:") for t in targets)
        # The toggle itself is still on screen, now pointing back at questions.
        assert any(t.startswith("toggle:sex:") and t.endswith(":q") for t in targets)

    @pytest.mark.asyncio
    async def test_toggle_only_applies_to_sex(self, handler, mock_query, session):
        """No other theme has two decks, so no other topic may toggle."""
        callback_data = ToggleCallbackData.parse("toggle:acq:0:t")

        await handler.handle(mock_query, callback_data, session)

        assert session.content_type == ContentType.QUESTIONS
        mock_query.edit_message_text.assert_called_once()
        assert _keyboard_of(mock_query.edit_message_text) is None


class TestBackHandler:
    """Test back handler."""

    @pytest.fixture
    def handler(self):
        """Create back handler."""
        return BackHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.fixture
    def session(self):
        return SessionState(
            language=Language.RUSSIAN, theme=Theme.ACQUAINTANCE, level=1
        )

    @pytest.mark.asyncio
    async def test_handle_back_to_themes(self, handler, mock_query, session):
        callback_data = BackCallbackData.parse("back:themes")

        await handler.handle(mock_query, callback_data, session)

        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("theme_") for t in targets)

    @pytest.mark.asyncio
    async def test_handle_back_to_calendar(self, handler, mock_query, session):
        callback_data = BackCallbackData.parse("back:calendar")

        await handler.handle(mock_query, callback_data, session)

        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("q:acq:1:") for t in targets)

    @pytest.mark.asyncio
    async def test_back_without_a_theme_lands_on_the_themes(
        self, handler, mock_query
    ):
        """Every destination needs a theme; without one, go up, not nowhere."""
        session = SessionState(language=Language.RUSSIAN)
        callback_data = BackCallbackData.parse("back:calendar")

        await handler.handle(mock_query, callback_data, session)

        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("theme_") for t in targets)

    @pytest.mark.asyncio
    async def test_unknown_destination_is_refused(self, handler, mock_query, session):
        callback_data = BackCallbackData.parse("back:elsewhere")

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()
        assert _keyboard_of(mock_query.edit_message_text) is None


class TestLanguageHandler:
    """Test language handler.

    There is one language left, so this handler no longer chooses anything:
    it is the landing point for every `lang_*` button still sitting in a
    user's chat history, and its job is to put them back on the welcome
    screen instead of failing.
    """

    @pytest.fixture
    def handler(self):
        """Create language handler."""
        return LanguageHandler()

    @pytest.fixture
    def mock_query(self):
        """Create mock callback query."""
        return _make_query()

    @pytest.mark.parametrize("code", ["ru", "en", "cs", "back"])
    @pytest.mark.asyncio
    async def test_handle_language_selection(self, handler, mock_query, code):
        """Any stored code reads as Russian and lands on the welcome screen."""
        session = SessionState(language=Language.RUSSIAN)
        callback_data = LanguageCallbackData.parse(f"lang_{code}")

        await handler.handle(mock_query, callback_data, session)

        assert session.language == Language.RUSSIAN
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
        return _make_query()

    @pytest.mark.asyncio
    async def test_handle_nsfw_confirm(self, handler, mock_query):
        """Confirming lands the player on the deck the warning was guarding."""
        session = SessionState(language=Language.RUSSIAN, theme=Theme.SEX)
        callback_data = SimpleCallbackData.parse("nsfw_confirm")

        await handler.handle(mock_query, callback_data, session)

        assert session.is_nsfw_confirmed is True
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("q:sex:") for t in targets)

    @pytest.mark.asyncio
    async def test_nsfw_confirm_on_a_levelled_theme_shows_its_levels(
        self, handler, mock_query
    ):
        """The branch for an NSFW theme that has levels.

        Sex is the only NSFW theme today and it has no levels, so nothing
        reaches this branch in production - which is exactly why it once
        called `_show_level_selection` with an argument missing and nobody
        noticed. One `nsfw: true` in a levelled theme's YAML would have made
        that a TypeError in front of a player.
        """
        session = SessionState(language=Language.RUSSIAN, theme=Theme.ACQUAINTANCE)
        callback_data = SimpleCallbackData.parse("nsfw_confirm")

        await handler.handle(mock_query, callback_data, session)

        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert targets == ["level_1", "level_2", "level_3", "back:themes"]

    @pytest.mark.asyncio
    async def test_nsfw_confirm_without_a_theme_is_refused(self, handler, mock_query):
        session = SessionState(language=Language.RUSSIAN)
        callback_data = SimpleCallbackData.parse("nsfw_confirm")

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_called_once()
        assert _keyboard_of(mock_query.edit_message_text) is None

    @pytest.mark.asyncio
    async def test_handle_nsfw_deny(self, handler, mock_query):
        """Declining goes back to the themes, not to a dead end."""
        session = SessionState(language=Language.RUSSIAN, theme=Theme.SEX)
        callback_data = SimpleCallbackData.parse("nsfw_deny")

        await handler.handle(mock_query, callback_data, session)

        assert session.is_nsfw_confirmed is False
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("theme_") for t in targets)

    @pytest.mark.asyncio
    async def test_handle_reset_game(self, handler, mock_query):
        """Reset asks first: the confirmation is the whole point of the step."""
        session = SessionState(language=Language.RUSSIAN)
        callback_data = SimpleCallbackData.parse("reset_game")

        await handler.handle(mock_query, callback_data, session)

        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert targets == ["reset_confirm", "reset_cancel"]

    @pytest.mark.asyncio
    async def test_handle_reset_confirm(self, handler, mock_query):
        """Confirming actually clears the stored session, not just the screen."""
        session = SessionState(language=Language.RUSSIAN, theme=Theme.SEX, level=2)
        callback_data = SimpleCallbackData.parse("reset_confirm")

        with patch(
            "vechnost_bot.callback_handlers.reset_session", new_callable=AsyncMock
        ) as mock_reset:
            await handler.handle(mock_query, callback_data, session)

        mock_reset.assert_awaited_once_with(12345)
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("theme_") for t in targets)

    @pytest.mark.asyncio
    async def test_handle_reset_cancel(self, handler, mock_query):
        """Cancelling touches no stored state and returns to the themes."""
        session = SessionState(language=Language.RUSSIAN, theme=Theme.SEX, level=2)
        callback_data = SimpleCallbackData.parse("reset_cancel")

        with patch(
            "vechnost_bot.callback_handlers.reset_session", new_callable=AsyncMock
        ) as mock_reset:
            await handler.handle(mock_query, callback_data, session)

        mock_reset.assert_not_awaited()
        assert session.theme == Theme.SEX
        targets = _callback_targets(_keyboard_of(mock_query.edit_message_text))
        assert any(t.startswith("theme_") for t in targets)

    @pytest.mark.asyncio
    async def test_handle_noop(self, handler, mock_query):
        """The filler buttons on a calendar page must do nothing at all."""
        session = SessionState(language=Language.RUSSIAN)
        callback_data = SimpleCallbackData.parse("noop")

        await handler.handle(mock_query, callback_data, session)

        mock_query.edit_message_text.assert_not_called()
        mock_query.edit_message_media.assert_not_called()
