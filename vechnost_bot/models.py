"""Data models for the Vechnost bot."""

from enum import Enum

from pydantic import BaseModel, Field


class Theme(str, Enum):
    """Available game themes."""

    ACQUAINTANCE = "Acquaintance"
    FOR_COUPLES = "For Couples"
    SEX = "Sex"
    PROVOCATION = "Provocation"


class ContentType(str, Enum):
    """Types of content available."""

    QUESTIONS = "questions"
    TASKS = "tasks"


class SessionState(BaseModel):
    """Current session state for a chat."""

    theme: Theme | None = None
    level: int | None = None
    content_type: ContentType = ContentType.QUESTIONS
    drawn_cards: set[str] = Field(default_factory=set)
    is_nsfw_confirmed: bool = False

    def reset(self) -> None:
        """Reset the session to initial state."""
        self.theme = None
        self.level = None
        self.content_type = ContentType.QUESTIONS
        self.drawn_cards.clear()
        self.is_nsfw_confirmed = False


class GameData(BaseModel):
    """Structure for loaded game data."""

    themes: dict[Theme, dict] = Field(default_factory=dict)

    def get_available_themes(self) -> list[Theme]:
        """Get list of available themes."""
        return list(self.themes.keys())

    def _has_levels_structure(self, theme: Theme) -> bool:
        """Check if theme uses the levels structure."""
        if theme not in self.themes:
            return False
        return "levels" in self.themes[theme]

    def get_available_levels(self, theme: Theme) -> list[int]:
        """Get available levels for a theme."""
        if theme not in self.themes:
            return []

        # For themes without levels (Sex, Provocation), return [1] as default
        if not self._has_levels_structure(theme):
            return [1]

        if "levels" not in self.themes[theme]:
            return []
        return sorted(self.themes[theme]["levels"].keys())

    def get_content(self, theme: Theme, level: int, content_type: ContentType) -> list[str]:
        """Get content for a specific theme, level, and type."""
        if theme not in self.themes:
            return []

        # For themes without levels (Sex, Provocation), get content directly
        if not self._has_levels_structure(theme):
            return self.themes[theme].get(content_type.value, [])

        # For themes with levels (Acquaintance, For Couples)
        if "levels" not in self.themes[theme]:
            return []
        if level not in self.themes[theme]["levels"]:
            return []
        return self.themes[theme]["levels"][level].get(content_type.value, [])

    def get_available_content_types(self, theme: Theme, level: int) -> list[ContentType]:
        """Get available content types for a theme and level."""
        if theme not in self.themes:
            return []

        available = []

        # For themes without levels (Sex, Provocation), check theme directly
        if not self._has_levels_structure(theme):
            if "questions" in self.themes[theme]:
                available.append(ContentType.QUESTIONS)
            if "tasks" in self.themes[theme]:
                available.append(ContentType.TASKS)
            return available

        # For themes with levels (Acquaintance, For Couples)
        if "levels" not in self.themes[theme]:
            return []
        if level not in self.themes[theme]["levels"]:
            return []

        level_data = self.themes[theme]["levels"][level]
        if "questions" in level_data:
            available.append(ContentType.QUESTIONS)
        if "tasks" in level_data:
            available.append(ContentType.TASKS)
        return available

    def has_nsfw_content(self, theme: Theme) -> bool:
        """Check if theme contains NSFW content."""
        return theme == Theme.SEX
