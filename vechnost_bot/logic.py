"""Game logic for the Vechnost bot."""

import random
from typing import Dict, Any

from .models import GameData, SessionState, Theme, ContentType
from .i18n import Language, i18n_manager


class LocalizedGameData:
    """Game data that loads content based on language."""

    def __init__(self):
        self._cached_data: Dict[Language, GameData] = {}

    def get_game_data(self, language: Language = Language.RUSSIAN) -> GameData:
        """Get game data for a specific language."""
        if language not in self._cached_data:
            self._cached_data[language] = self._load_game_data_for_language(language)
        return self._cached_data[language]

    def _load_game_data_for_language(self, language: Language) -> GameData:
        """Load game data for a specific language."""
        from pathlib import Path
        import yaml

        # Try to load translated content first
        if language != Language.RUSSIAN:
            translated_file = Path(__file__).parent.parent / "data" / f"questions_{language.value}.yaml"
            if translated_file.exists():
                try:
                    with open(translated_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    return self._create_game_data_from_yaml(data)
                except Exception as e:
                    print(f"Failed to load translated content for {language.value}: {e}")

        # Fallback to Russian (original) content
        yaml_path = Path(__file__).parent.parent / "data" / "questions.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return self._create_game_data_from_yaml(data)

    def _create_game_data_from_yaml(self, data: Dict[str, Any]) -> GameData:
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

    def get_content(self, theme: Theme, level: int | None, content_type: ContentType, language: Language = Language.RUSSIAN) -> list[str]:
        """Get content for a specific theme, level, and content type in the specified language."""
        game_data = self.get_game_data(language)
        return game_data.get_content(theme, level, content_type)

    def get_available_levels(self, theme: Theme, language: Language = Language.RUSSIAN) -> list[int]:
        """Get available levels for a theme in the specified language."""
        game_data = self.get_game_data(language)
        return game_data.get_available_levels(theme)

    def get_total_cards_in_level(self, theme: Theme, level: int, content_type: ContentType, language: Language = Language.RUSSIAN) -> int:
        """Get total number of cards in a level for the specified language."""
        game_data = self.get_game_data(language)
        return game_data.get_total_cards_in_level(theme, level, content_type)

    def has_nsfw_content(self, theme: Theme, language: Language = Language.RUSSIAN) -> bool:
        """Check if theme has NSFW content."""
        game_data = self.get_game_data(language)
        return game_data.has_nsfw_content(theme)


# Global instance
localized_game_data = LocalizedGameData()


def load_game_data() -> GameData:
    """Load game data from YAML file (deprecated - use localized_game_data instead)."""
    return localized_game_data.get_game_data(Language.RUSSIAN)


def draw_card(
    session: SessionState,
    game_data: GameData
) -> str | None:
    """Draw a random card that hasn't been drawn yet."""
    if not session.theme:
        return None

    # For themes without levels, level can be None
    level = session.level if game_data._has_levels_structure(session.theme) else None

    available_content = game_data.get_content(
        session.theme,
        level,
        session.content_type
    )

    if not available_content:
        return None

    # Filter out already drawn cards
    undrawn_cards = [card for card in available_content if card not in session.drawn_cards]

    if not undrawn_cards:
        return None

    # Draw a random card
    drawn_card = random.choice(undrawn_cards)
    session.drawn_cards.add(drawn_card)

    return drawn_card


def get_remaining_cards_count(session: SessionState, game_data: GameData) -> int:
    """Get the number of remaining cards for the current session."""
    if not session.theme:
        return 0

    # For themes without levels, level can be None
    level = session.level if game_data._has_levels_structure(session.theme) else None

    available_content = game_data.get_content(
        session.theme,
        level,
        session.content_type
    )

    if not available_content:
        return 0

    undrawn_cards = [card for card in available_content if card not in session.drawn_cards]
    return len(undrawn_cards)


def can_draw_card(session: SessionState, game_data: GameData) -> bool:
    """Check if a card can be drawn in the current session."""
    return get_remaining_cards_count(session, game_data) > 0


def is_session_complete(session: SessionState, game_data: GameData) -> bool:
    """Check if the current session is complete (no more cards to draw)."""
    return not can_draw_card(session, game_data)


def validate_session(session: SessionState, game_data: GameData) -> bool:
    """Validate that the current session state is valid."""
    if not session.theme:
        return False

    # Check if theme exists
    if session.theme not in game_data.themes:
        return False

    # For themes without levels (Sex, Provocation), level should be None
    if not game_data._has_levels_structure(session.theme):
        if session.level is not None:
            return False
    else:
        # For themes with levels (Acquaintance, For Couples)
        if not session.level:
            return False
        if "levels" not in game_data.themes[session.theme]:
            return False
        if session.level not in game_data.themes[session.theme]["levels"]:
            return False

    # Check if content type is available
    level = session.level if game_data._has_levels_structure(session.theme) else None
    available_types = game_data.get_available_content_types(session.theme, level)
    if session.content_type not in available_types:
        return False

    return True
