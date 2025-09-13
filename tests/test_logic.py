"""Tests for game logic."""

from vechnost_bot.logic import (
    can_draw_card,
    draw_card,
    get_remaining_cards_count,
    is_session_complete,
    load_game_data,
    validate_session,
)
from vechnost_bot.models import ContentType, GameData, SessionState, Theme


class TestGameLogic:
    """Test game logic functionality."""

    def test_load_game_data(self):
        """Test loading game data from YAML."""
        game_data = load_game_data()

        assert isinstance(game_data, GameData)
        assert len(game_data.themes) > 0

        # Check that all expected themes are present
        expected_themes = [Theme.ACQUAINTANCE, Theme.FOR_COUPLES, Theme.SEX, Theme.PROVOCATION]
        for theme in expected_themes:
            assert theme in game_data.themes

    def test_validate_session_valid(self):
        """Test validating a valid session."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS

        assert validate_session(session, game_data) is True

    def test_validate_session_invalid_theme(self):
        """Test validating session with invalid theme."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.SEX  # Not in game_data
        session.level = 1
        session.content_type = ContentType.QUESTIONS

        assert validate_session(session, game_data) is False

    def test_validate_session_invalid_level(self):
        """Test validating session with invalid level."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 2  # Not in game_data
        session.content_type = ContentType.QUESTIONS

        assert validate_session(session, game_data) is False

    def test_validate_session_invalid_content_type(self):
        """Test validating session with invalid content type."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.TASKS  # Not available

        assert validate_session(session, game_data) is False

    def test_get_remaining_cards_count(self):
        """Test getting remaining cards count."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2", "q3"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS

        # No cards drawn yet
        assert get_remaining_cards_count(session, game_data) == 3

        # Draw one card
        session.drawn_cards.add("q1")
        assert get_remaining_cards_count(session, game_data) == 2

        # Draw all cards
        session.drawn_cards.update(["q2", "q3"])
        assert get_remaining_cards_count(session, game_data) == 0

    def test_can_draw_card(self):
        """Test checking if card can be drawn."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS

        # Can draw initially
        assert can_draw_card(session, game_data) is True

        # Draw all cards
        session.drawn_cards.update(["q1", "q2"])
        assert can_draw_card(session, game_data) is False

    def test_draw_card(self):
        """Test drawing a card."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2", "q3"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS

        # Draw first card
        card = draw_card(session, game_data)
        assert card in ["q1", "q2", "q3"]
        assert card in session.drawn_cards
        assert len(session.drawn_cards) == 1

        # Draw second card
        card2 = draw_card(session, game_data)
        assert card2 != card
        assert card2 in session.drawn_cards
        assert len(session.drawn_cards) == 2

    def test_draw_card_no_cards_available(self):
        """Test drawing when no cards available."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS
        session.drawn_cards.update(["q1", "q2"])

        card = draw_card(session, game_data)
        assert card is None

    def test_draw_card_invalid_session(self):
        """Test drawing with invalid session."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()  # No theme/level set

        card = draw_card(session, game_data)
        assert card is None

    def test_is_session_complete(self):
        """Test checking if session is complete."""
        game_data = GameData(themes={
            Theme.ACQUAINTANCE: {"levels": {1: {"questions": ["q1", "q2"]}}}
        })

        session = SessionState()
        session.theme = Theme.ACQUAINTANCE
        session.level = 1
        session.content_type = ContentType.QUESTIONS

        # Not complete initially
        assert is_session_complete(session, game_data) is False

        # Complete after drawing all cards
        session.drawn_cards.update(["q1", "q2"])
        assert is_session_complete(session, game_data) is True
