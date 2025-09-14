"""Tests for YAML data integrity."""

from vechnost_bot.logic import load_game_data
from vechnost_bot.models import Theme


class TestYAMLIntegrity:
    """Test YAML data integrity and structure."""

    def test_yaml_loads_successfully(self):
        """Test that YAML file loads without errors."""
        game_data = load_game_data()
        assert game_data is not None
        assert len(game_data.themes) > 0

    def test_all_themes_present(self):
        """Test that all expected themes are present."""
        game_data = load_game_data()
        expected_themes = [Theme.ACQUAINTANCE, Theme.FOR_COUPLES, Theme.SEX, Theme.PROVOCATION]

        for theme in expected_themes:
            assert theme in game_data.themes, f"Theme {theme} not found in data"

    def test_acquaintance_theme_structure(self):
        """Test Acquaintance theme structure."""
        game_data = load_game_data()
        theme = Theme.ACQUAINTANCE

        assert theme in game_data.themes
        theme_data = game_data.themes[theme]

        # Should have levels key
        assert "levels" in theme_data

        # Should have 3 levels
        assert 1 in theme_data["levels"]
        assert 2 in theme_data["levels"]
        assert 3 in theme_data["levels"]

        # Each level should have questions
        for level in [1, 2, 3]:
            level_data = theme_data["levels"][level]
            assert "questions" in level_data
            assert isinstance(level_data["questions"], list)
            assert len(level_data["questions"]) > 0

    def test_for_couples_theme_structure(self):
        """Test For Couples theme structure."""
        game_data = load_game_data()
        theme = Theme.FOR_COUPLES

        assert theme in game_data.themes
        theme_data = game_data.themes[theme]

        # Should have levels key
        assert "levels" in theme_data

        # Should have 3 levels
        assert 1 in theme_data["levels"]
        assert 2 in theme_data["levels"]
        assert 3 in theme_data["levels"]

        # Each level should have questions
        for level in [1, 2, 3]:
            level_data = theme_data["levels"][level]
            assert "questions" in level_data
            assert isinstance(level_data["questions"], list)
            assert len(level_data["questions"]) > 0

    def test_sex_theme_structure(self):
        """Test Sex theme structure."""
        game_data = load_game_data()
        theme = Theme.SEX

        assert theme in game_data.themes
        theme_data = game_data.themes[theme]

        # Sex theme should NOT have levels key (direct structure)
        assert "levels" not in theme_data

        # Should have questions and tasks directly
        assert "questions" in theme_data
        assert "tasks" in theme_data

        assert isinstance(theme_data["questions"], list)
        assert isinstance(theme_data["tasks"], list)
        assert len(theme_data["questions"]) > 0
        assert len(theme_data["tasks"]) > 0

    def test_provocation_theme_structure(self):
        """Test Provocation theme structure."""
        game_data = load_game_data()
        theme = Theme.PROVOCATION

        assert theme in game_data.themes
        theme_data = game_data.themes[theme]

        # Provocation theme should NOT have levels key (direct structure)
        assert "levels" not in theme_data

        # Should have questions directly
        assert "questions" in theme_data
        assert isinstance(theme_data["questions"], list)
        assert len(theme_data["questions"]) > 0

    def test_no_empty_strings_in_content(self):
        """Test that no content contains empty strings."""
        game_data = load_game_data()

        for theme, theme_data in game_data.themes.items():
            if "levels" in theme_data:
                for level, level_data in theme_data["levels"].items():
                    for content_type in ["questions", "tasks"]:
                        if content_type in level_data:
                            content = level_data[content_type]
                            for item in content:
                                assert item.strip() != "", f"Empty string found in {theme} level {level} {content_type}"

    def test_tasks_only_in_sex_theme(self):
        """Test that tasks are only present in Sex theme."""
        game_data = load_game_data()

        for theme, theme_data in game_data.themes.items():
            if "levels" in theme_data:
                for _level, level_data in theme_data["levels"].items():
                    if "tasks" in level_data:
                        assert theme == Theme.SEX, f"Tasks found in non-Sex theme: {theme}"

    def test_content_types_consistency(self):
        """Test that content types are consistent across levels."""
        game_data = load_game_data()

        for theme, theme_data in game_data.themes.items():
            if "levels" in theme_data:
                content_types = set()
                for _level, level_data in theme_data["levels"].items():
                    level_content_types = set(level_data.keys())
                    content_types.update(level_content_types)

                # All levels should have the same content types
                for _level, level_data in theme_data["levels"].items():
                    level_content_types = set(level_data.keys())
                    assert level_content_types == content_types, f"Inconsistent content types in {theme}"

    def test_questions_have_content(self):
        """Test that all question lists have actual content."""
        game_data = load_game_data()

        for theme, theme_data in game_data.themes.items():
            if "levels" in theme_data:
                for level, level_data in theme_data["levels"].items():
                    if "questions" in level_data:
                        questions = level_data["questions"]
                        assert len(questions) > 0, f"No questions in {theme} level {level}"

                        # Check that questions are not just level indicators (skip first item as it might be a level indicator)
                        for i, question in enumerate(questions):
                            if i == 0 and question.strip() in ("1 уровень", "2 уровень", "3 уровень"):
                                continue  # Skip level indicators at the beginning
                            assert question.strip() != "", f"Empty question found in {theme} level {level}"

    def test_tasks_have_content(self):
        """Test that all task lists have actual content."""
        game_data = load_game_data()

        for theme, theme_data in game_data.themes.items():
            if "levels" in theme_data:
                for level, level_data in theme_data["levels"].items():
                    if "tasks" in level_data:
                        tasks = level_data["tasks"]
                        assert len(tasks) > 0, f"No tasks in {theme} level {level}"

                        # Check that tasks are not just level indicators (skip first item as it might be a level indicator)
                        for i, task in enumerate(tasks):
                            if i == 0 and task.strip() in ("1 уровень", "2 уровень", "3 уровень"):
                                continue  # Skip level indicators at the beginning
                            assert task.strip() != "", f"Empty task found in {theme} level {level}"
