"""Tests for callback data models."""

import pytest
from pydantic import ValidationError

from vechnost_bot.callback_models import (
    BackCallbackData,
    CalendarCallbackData,
    CallbackAction,
    CallbackData,
    LevelCallbackData,
    NavigationCallbackData,
    QuestionCallbackData,
    SimpleCallbackData,
    ThemeCallbackData,
    ToggleCallbackData,
)


class TestCallbackData:
    """Test CallbackData base class."""

    def test_parse_theme_callback(self):
        """Test parsing theme callback data."""
        data = "theme_Acquaintance"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, ThemeCallbackData)
        assert callback_data.action == CallbackAction.THEME
        assert callback_data.theme_name == "Acquaintance"
        assert callback_data.raw_data == data

    def test_parse_level_callback(self):
        """Test parsing level callback data."""
        data = "level_2"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, LevelCallbackData)
        assert callback_data.action == CallbackAction.LEVEL
        assert callback_data.level == 2
        assert callback_data.raw_data == data

    def test_parse_calendar_callback(self):
        """Test parsing calendar callback data."""
        data = "cal:acq:1:q:0"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, CalendarCallbackData)
        assert callback_data.action == CallbackAction.CALENDAR
        assert callback_data.topic == "acq"
        assert callback_data.level_or_0 == 1
        assert callback_data.category == "q"
        assert callback_data.page == 0
        assert callback_data.raw_data == data

    def test_parse_question_callback(self):
        """Test parsing question callback data."""
        data = "q:acq:1:5"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, QuestionCallbackData)
        assert callback_data.action == CallbackAction.QUESTION
        assert callback_data.topic == "acq"
        assert callback_data.level_or_0 == 1
        assert callback_data.index == 5
        assert callback_data.raw_data == data

    def test_parse_navigation_callback(self):
        """Test parsing navigation callback data."""
        data = "nav:acq:1:6"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, NavigationCallbackData)
        assert callback_data.action == CallbackAction.NAVIGATION
        assert callback_data.topic == "acq"
        assert callback_data.level_or_0 == 1
        assert callback_data.index == 6
        assert callback_data.raw_data == data

    def test_parse_toggle_callback(self):
        """Test parsing toggle callback data."""
        data = "toggle:sex:0:t"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, ToggleCallbackData)
        assert callback_data.action == CallbackAction.TOGGLE
        assert callback_data.topic == "sex"
        assert callback_data.category == "t"
        assert callback_data.page == 0
        assert callback_data.raw_data == data

    def test_parse_back_callback(self):
        """Test parsing back callback data."""
        data = "back:themes"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, BackCallbackData)
        assert callback_data.action == CallbackAction.BACK
        assert callback_data.destination == "themes"
        assert callback_data.raw_data == data

    def test_parse_simple_callback(self):
        """Test parsing simple callback data."""
        data = "nsfw_confirm"
        callback_data = CallbackData.parse(data)

        assert isinstance(callback_data, SimpleCallbackData)
        assert callback_data.action == CallbackAction.NSFW_CONFIRM
        assert callback_data.raw_data == data

    def test_parse_invalid_data(self):
        """Test parsing invalid callback data."""
        with pytest.raises(ValueError, match="Invalid callback data"):
            CallbackData.parse("")

        with pytest.raises(ValueError, match="Invalid callback data"):
            CallbackData.parse("x" * 101)  # Too long

        with pytest.raises(ValueError, match="Potentially malicious callback data"):
            CallbackData.parse("theme_../../../etc/passwd")

        with pytest.raises(ValueError, match="Unknown callback action"):
            CallbackData.parse("unknown_action")


class TestThemeCallbackData:
    """Test ThemeCallbackData model."""

    def test_parse_valid_theme(self):
        """Test parsing valid theme data."""
        data = "theme_Acquaintance"
        callback_data = ThemeCallbackData.parse(data)

        assert callback_data.action == CallbackAction.THEME
        assert callback_data.theme_name == "Acquaintance"
        assert callback_data.raw_data == data

    def test_parse_invalid_theme(self):
        """Test parsing invalid theme data."""
        with pytest.raises(ValueError, match="Invalid theme callback data"):
            ThemeCallbackData.parse("invalid_theme")

        with pytest.raises(ValueError, match="Empty theme name"):
            ThemeCallbackData.parse("theme_")


class TestLevelCallbackData:
    """Test LevelCallbackData model."""

    def test_parse_valid_level(self):
        """Test parsing valid level data."""
        data = "level_3"
        callback_data = LevelCallbackData.parse(data)

        assert callback_data.action == CallbackAction.LEVEL
        assert callback_data.level == 3
        assert callback_data.raw_data == data

    def test_parse_invalid_level(self):
        """Test parsing invalid level data."""
        with pytest.raises(ValueError, match="Invalid level callback data"):
            LevelCallbackData.parse("invalid_level")

        with pytest.raises(ValueError, match="Invalid level number"):
            LevelCallbackData.parse("level_abc")

        with pytest.raises(ValueError, match="Level out of range"):
            LevelCallbackData.parse("level_0")

        with pytest.raises(ValueError, match="Level out of range"):
            LevelCallbackData.parse("level_11")


class TestCalendarCallbackData:
    """Test CalendarCallbackData model."""

    def test_parse_valid_calendar(self):
        """Test parsing valid calendar data."""
        data = "cal:acq:2:q:1"
        callback_data = CalendarCallbackData.parse(data)

        assert callback_data.action == CallbackAction.CALENDAR
        assert callback_data.topic == "acq"
        assert callback_data.level_or_0 == 2
        assert callback_data.category == "q"
        assert callback_data.page == 1
        assert callback_data.raw_data == data

    def test_parse_invalid_calendar(self):
        """Test parsing invalid calendar data."""
        with pytest.raises(ValueError, match="Invalid calendar callback data"):
            CalendarCallbackData.parse("invalid_calendar")

        with pytest.raises(ValueError, match="Invalid calendar callback format"):
            CalendarCallbackData.parse("cal:acq:2:q")

        with pytest.raises(ValueError, match="Invalid numeric values"):
            CalendarCallbackData.parse("cal:acq:abc:q:1")

        with pytest.raises(ValueError, match="Invalid category"):
            CalendarCallbackData.parse("cal:acq:2:x:1")

        with pytest.raises(ValueError, match="Level out of range"):
            CalendarCallbackData.parse("cal:acq:-1:q:1")

        with pytest.raises(ValueError, match="Page out of range"):
            CalendarCallbackData.parse("cal:acq:2:q:-1")


class TestQuestionCallbackData:
    """Test QuestionCallbackData model."""

    def test_parse_valid_question(self):
        """Test parsing valid question data."""
        data = "q:acq:1:10"
        callback_data = QuestionCallbackData.parse(data)

        assert callback_data.action == CallbackAction.QUESTION
        assert callback_data.topic == "acq"
        assert callback_data.level_or_0 == 1
        assert callback_data.index == 10
        assert callback_data.raw_data == data

    def test_parse_invalid_question(self):
        """Test parsing invalid question data."""
        with pytest.raises(ValueError, match="Invalid question callback data"):
            QuestionCallbackData.parse("invalid_question")

        with pytest.raises(ValueError, match="Invalid question callback format"):
            QuestionCallbackData.parse("q:acq:1")

        with pytest.raises(ValueError, match="Invalid numeric values"):
            QuestionCallbackData.parse("q:acq:abc:10")

        with pytest.raises(ValueError, match="Level out of range"):
            QuestionCallbackData.parse("q:acq:-1:10")

        with pytest.raises(ValueError, match="Index out of range"):
            QuestionCallbackData.parse("q:acq:1:-1")


class TestNavigationCallbackData:
    """Test NavigationCallbackData model."""

    def test_parse_valid_navigation(self):
        """Test parsing valid navigation data."""
        data = "nav:acq:1:5"
        callback_data = NavigationCallbackData.parse(data)

        assert callback_data.action == CallbackAction.NAVIGATION
        assert callback_data.topic == "acq"
        assert callback_data.level_or_0 == 1
        assert callback_data.index == 5
        assert callback_data.raw_data == data

    def test_parse_invalid_navigation(self):
        """Test parsing invalid navigation data."""
        with pytest.raises(ValueError, match="Invalid navigation callback data"):
            NavigationCallbackData.parse("invalid_navigation")

        with pytest.raises(ValueError, match="Invalid navigation callback format"):
            NavigationCallbackData.parse("nav:acq:1")

        with pytest.raises(ValueError, match="Invalid numeric values"):
            NavigationCallbackData.parse("nav:acq:abc:5")

        with pytest.raises(ValueError, match="Level out of range"):
            NavigationCallbackData.parse("nav:acq:-1:5")

        with pytest.raises(ValueError, match="Index out of range"):
            NavigationCallbackData.parse("nav:acq:1:-1")


class TestToggleCallbackData:
    """Test ToggleCallbackData model."""

    def test_parse_valid_toggle(self):
        """Test parsing valid toggle data."""
        data = "toggle:sex:0:q"
        callback_data = ToggleCallbackData.parse(data)

        assert callback_data.action == CallbackAction.TOGGLE
        assert callback_data.topic == "sex"
        assert callback_data.category == "q"
        assert callback_data.page == 0
        assert callback_data.raw_data == data

    def test_parse_invalid_toggle(self):
        """Test parsing invalid toggle data."""
        with pytest.raises(ValueError, match="Invalid toggle callback data"):
            ToggleCallbackData.parse("invalid_toggle")

        with pytest.raises(ValueError, match="Invalid toggle callback format"):
            ToggleCallbackData.parse("toggle:sex:q")

        with pytest.raises(ValueError, match="invalid literal for int"):
            ToggleCallbackData.parse("toggle:sex:abc:q")

        with pytest.raises(ValueError, match="Invalid category"):
            ToggleCallbackData.parse("toggle:sex:0:x")

        with pytest.raises(ValueError, match="Page out of range"):
            ToggleCallbackData.parse("toggle:sex:-1:q")


class TestBackCallbackData:
    """Test BackCallbackData model."""

    def test_parse_valid_back(self):
        """Test parsing valid back data."""
        data = "back:themes"
        callback_data = BackCallbackData.parse(data)

        assert callback_data.action == CallbackAction.BACK
        assert callback_data.destination == "themes"
        assert callback_data.raw_data == data

    def test_parse_invalid_back(self):
        """Test parsing invalid back data."""
        with pytest.raises(ValueError, match="Invalid back callback data"):
            BackCallbackData.parse("invalid_back")

        with pytest.raises(ValueError, match="Invalid back callback data"):
            BackCallbackData.parse("back")

        with pytest.raises(ValueError, match="Empty back destination"):
            BackCallbackData.parse("back:")


class TestSimpleCallbackData:
    """Test SimpleCallbackData model."""

    def test_parse_valid_simple(self):
        """Test parsing valid simple data."""
        data = "nsfw_confirm"
        callback_data = SimpleCallbackData.parse(data)

        assert callback_data.action == CallbackAction.NSFW_CONFIRM
        assert callback_data.raw_data == data

    def test_parse_invalid_simple(self):
        """Test parsing invalid simple data."""
        with pytest.raises(ValueError, match="Unknown simple action"):
            SimpleCallbackData.parse("unknown_action")
