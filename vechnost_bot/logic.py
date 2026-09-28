"""Game logic for the Vechnost bot."""

from typing import Any

from .i18n import Language
from .models import ContentType, GameData, Theme


class LocalizedGameData:
    """Game data that loads content based on language."""

    def __init__(self) -> None:
        self._cached_data: dict[Language, GameData] = {}

    def get_game_data(self, language: Language = Language.RUSSIAN) -> GameData:
        """Get game data for a specific language."""
        if language not in self._cached_data:
            self._cached_data[language] = self._load_game_data_for_language(language)
        return self._cached_data[language]

    def _load_game_data_for_language(self, language: Language) -> GameData:
        """Load the one shipped content set.

        `language` survives as the cache key its callers still pass, not as a
        branch: there is a single deck file. The `questions_{lang}.yaml` files
        this used to prefer are deleted, so the branch that looked for them
        could not be taken.
        """
        from pathlib import Path

        import yaml

        yaml_path = Path(__file__).parent.parent / "data" / "questions.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return self._create_game_data_from_yaml(data)

    def _create_game_data_from_yaml(self, data: dict[str, Any]) -> GameData:
        """Create GameData from YAML data."""
        themes = {}
        for theme_name, theme_data in data.get("themes", {}).items():
            try:
                theme = Theme(theme_name)
                themes[theme] = theme_data
            except ValueError:
                # Skip unknown themes
                continue
        return GameData(themes=themes)

    def get_content(
        self,
        theme: Theme,
        level: int | None,
        content_type: ContentType,
        language: Language = Language.RUSSIAN,
    ) -> list[str]:
        """Get content for a specific theme, level, and content type in the specified language."""
        game_data = self.get_game_data(language)
        return game_data.get_content(theme, level, content_type)

    def get_available_levels(
        self, theme: Theme, language: Language = Language.RUSSIAN
    ) -> list[int]:
        """Get available levels for a theme in the specified language."""
        game_data = self.get_game_data(language)
        return game_data.get_available_levels(theme)

    def has_nsfw_content(self, theme: Theme, language: Language = Language.RUSSIAN) -> bool:
        """Check if theme has NSFW content."""
        game_data = self.get_game_data(language)
        return game_data.has_nsfw_content(theme)


# Global instance
localized_game_data = LocalizedGameData()
