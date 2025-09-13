"""Tests for data models."""

from vechnost_bot.models import ContentType, GameData, SessionState, Theme


class TestSessionState:
    """Test SessionState model."""

    def test_default_values(self):
        """Test default values for new session."""
        session = SessionState()
        assert session.theme is None
        assert session.level is None
        assert session.content_type == ContentType.QUESTIONS
        assert session.drawn_cards == set()
        assert session.is_nsfw_confirmed is False

    def test_reset(self):
        """Test session reset functionality."""
        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.TASKS
        session.drawn_cards.add("test_card")
        session.is_nsfw_confirmed = True

        session.reset()

        assert session.theme is None
        assert session.level is None
        assert session.content_type == ContentType.QUESTIONS
        assert session.drawn_cards == set()
        assert session.is_nsfw_confirmed is False


class TestGameData:
    """Test GameData model."""

    def test_empty_game_data(self):
        """Test empty game data."""
        game_data = GameData()
        assert game_data.themes == {}
        assert game_data.get_available_themes() == []

    def test_get_available_themes(self):
        """Test getting available themes."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1"]}}},
            Theme.SEX: {"levels": {1: {"questions": ["q2"], "tasks": ["t1"]}}},
        })

        themes = game_data.get_available_themes()
        assert Theme.ACQUAINTANCE in themes
        assert Theme.SEX in themes
        assert len(themes) == 2

    def test_get_available_levels(self):
        """Test getting available levels for a theme."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {
                "levels": {
                    1: {"questions": ["q1"]},
                    2: {"questions": ["q2"]},
                    3: {"questions": ["q3"]},
                }
            }
        })

        levels = game_data.get_available_levels(Theme.ACQUAINTANCE)
        assert levels == [1, 2, 3]

        # Test non-existent theme
        levels = game_data.get_available_levels(Theme.PROVOCATION)
        assert levels == []

    def test_get_content(self):
        """Test getting content for theme/level/type."""
        game_data = GameData(themes={
            Theme.SEX: {
                "levels": {
                    1: {
                        "questions": ["q1", "q2"],
                        "tasks": ["t1", "t2"]
                    }
                }
            }
        })

        questions = game_data.get_content(Theme.SEX, 1, ContentType.QUESTIONS)
        assert questions == ["q1", "q2"]

        tasks = game_data.get_content(Theme.SEX, 1, ContentType.TASKS)
        assert tasks == ["t1", "t2"]

        # Test non-existent content
        questions = game_data.get_content(Theme.ACQUAINTANCE, 1, ContentType.QUESTIONS)
        assert questions == []

    def test_get_available_content_types(self):
        """Test getting available content types."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1"]}}},
            Theme.SEX: {"levels": {1: {"questions": ["q1"], "tasks": ["t1"]}}},
        })

        # Theme with only questions
        types = game_data.get_available_content_types(Theme.ACQUAINTANCE, 1)
        assert types == [ContentType.QUESTIONS]

        # Theme with both questions and tasks
        types = game_data.get_available_content_types(Theme.SEX, 1)
        assert ContentType.QUESTIONS in types
        assert ContentType.TASKS in types
        assert len(types) == 2

    def test_has_nsfw_content(self):
        """Test NSFW content detection."""
        game_data = GameData()

        assert game_data.has_nsfw_content(Theme.SEX) is True
        assert game_data.has_nsfw_content(Theme.ACQUAINTANCE) is False
        assert game_data.has_nsfw_content(Theme.FOR_COUPLES) is False
        assert game_data.has_nsfw_content(Theme.PROVOCATION) is False
