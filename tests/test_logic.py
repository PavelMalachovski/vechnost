"""Tests for game logic."""

from vechnost_bot.logic import localized_game_data
from vechnost_bot.models import GameData, Theme


class TestGameLogic:
    """Test game logic functionality."""

    def test_load_game_data(self):
        """Test loading game data from YAML."""
        game_data = localized_game_data.get_game_data()

        assert isinstance(game_data, GameData)
        assert len(game_data.themes) > 0

        # Check that all expected themes are present
        expected_themes = [Theme.ACQUAINTANCE, Theme.FOR_COUPLES, Theme.SEX, Theme.PROVOCATION]
        for theme in expected_themes:
            assert theme in game_data.themes
