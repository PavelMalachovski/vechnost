"""Internationalization (i18n) support for the Vechnost bot."""

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from babel import Locale
from babel.support import Format

logger = logging.getLogger(__name__)


class Language(str, Enum):
    """Supported languages."""
    RUSSIAN = "ru"
    ENGLISH = "en"
    CZECH = "cs"


class I18nManager:
    """Manages internationalization for the bot."""

    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.translations: Dict[Language, Dict[str, Any]] = {}
        self.formatters: Dict[Language, Format] = {}
        self._load_translations()
        self._setup_formatters()

    def _load_translations(self) -> None:
        """Load all translation files."""
        for language in Language:
            try:
                # Load UI translations
                ui_file = self.data_dir / f"translations_{language.value}.yaml"
                if ui_file.exists():
                    with open(ui_file, 'r', encoding='utf-8') as f:
                        ui_translations = yaml.safe_load(f) or {}
                else:
                    ui_translations = {}

                # Load questions translations
                questions_file = self.data_dir / f"questions_{language.value}.yaml"
                if questions_file.exists():
                    with open(questions_file, 'r', encoding='utf-8') as f:
                        questions_translations = yaml.safe_load(f) or {}
                else:
                    questions_translations = {}

                # Merge translations
                self.translations[language] = {
                    "ui": ui_translations,
                    "questions": questions_translations
                }

                logger.info(f"Loaded translations for {language.value}")

            except Exception as e:
                logger.error(f"Failed to load translations for {language.value}: {e}")
                self.translations[language] = {}

    def _setup_formatters(self) -> None:
        """Setup Babel formatters for each language."""
        for language in Language:
            try:
                locale = Locale(language.value)
                self.formatters[language] = Format(locale)
            except Exception as e:
                logger.error(f"Failed to setup formatter for {language.value}: {e}")
                # Fallback to English
                self.formatters[language] = Format(Locale('en'))

    def get_text(self, key: str, language: Language = Language.RUSSIAN, **kwargs) -> str:
        """Get translated text for a key."""
        try:
            # Navigate through nested keys (e.g., "welcome.title")
            keys = key.split('.')
            value = self.translations.get(language, {}).get("ui", {})

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    # Fallback to Russian if key not found
                    if language != Language.RUSSIAN:
                        return self.get_text(key, Language.RUSSIAN, **kwargs)
                    else:
                        logger.warning(f"Translation key not found: {key}")
                        return key

            # Format the text if it's a string and kwargs are provided
            if isinstance(value, str) and kwargs:
                try:
                    return value.format(**kwargs)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to format text for key {key}: {e}")
                    return value

            return str(value) if value is not None else key

        except Exception as e:
            logger.error(f"Error getting text for key {key}: {e}")
            return key

    def get_questions(self, theme: str, level: int, content_type: str, language: Language = Language.RUSSIAN) -> list[str]:
        """Get translated questions for a theme and level."""
        try:
            questions_data = self.translations.get(language, {}).get("questions", {})
            themes = questions_data.get("themes", {})
            theme_data = themes.get(theme, {})
            levels = theme_data.get("levels", {})
            level_data = levels.get(str(level), {})
            content = level_data.get(content_type, [])

            if not content and language != Language.RUSSIAN:
                # Fallback to Russian
                return self.get_questions(theme, level, content_type, Language.RUSSIAN)

            return content if isinstance(content, list) else []

        except Exception as e:
            logger.error(f"Error getting questions for {theme}/{level}/{content_type}: {e}")
            return []

    def get_available_themes(self, language: Language = Language.RUSSIAN) -> Dict[str, str]:
        """Get available themes with their translated names."""
        try:
            themes_data = self.translations.get(language, {}).get("themes", {})
            return themes_data
        except Exception as e:
            logger.error(f"Error getting themes for {language.value}: {e}")
            return {}

    def format_number(self, number: int, language: Language = Language.RUSSIAN) -> str:
        """Format a number according to locale rules."""
        try:
            formatter = self.formatters.get(language)
            if formatter:
                return formatter.number(number)
            return str(number)
        except Exception as e:
            logger.error(f"Error formatting number {number} for {language.value}: {e}")
            return str(number)

    def get_language_name(self, language: Language, target_language: Language = Language.RUSSIAN) -> str:
        """Get the display name of a language in the target language."""
        language_names = {
            Language.RUSSIAN: {
                Language.RUSSIAN: "Русский",
                Language.ENGLISH: "Russian",
                Language.CZECH: "Ruština"
            },
            Language.ENGLISH: {
                Language.RUSSIAN: "Английский",
                Language.ENGLISH: "English",
                Language.CZECH: "Angličtina"
            },
            Language.CZECH: {
                Language.RUSSIAN: "Чешский",
                Language.ENGLISH: "Czech",
                Language.CZECH: "Čeština"
            }
        }

        return language_names.get(language, {}).get(target_language, language.value)


# Global i18n manager instance
i18n_manager = I18nManager()


# Convenience functions
def get_text(key: str, language: Language = Language.RUSSIAN, **kwargs) -> str:
    """Get translated text for a key."""
    return i18n_manager.get_text(key, language, **kwargs)


def get_questions(theme: str, level: int, content_type: str, language: Language = Language.RUSSIAN) -> list[str]:
    """Get translated questions for a theme and level."""
    return i18n_manager.get_questions(theme, level, content_type, language)


def get_available_themes(language: Language = Language.RUSSIAN) -> Dict[str, str]:
    """Get available themes with their translated names."""
    return i18n_manager.get_available_themes(language)


def format_number(number: int, language: Language = Language.RUSSIAN) -> str:
    """Format a number according to locale rules."""
    return i18n_manager.format_number(number, language)


def get_language_name(language: Language, target_language: Language = Language.RUSSIAN) -> str:
    """Get the display name of a language in the target language."""
    return i18n_manager.get_language_name(language, target_language)


# Language detection utilities
def detect_language_from_text(text: str) -> Language:
    """Simple language detection based on text content."""
    text_lower = text.lower()

    # Czech indicators
    czech_indicators = ['č', 'ř', 'ž', 'š', 'ď', 'ť', 'ň', 'ů', 'ý', 'á', 'í', 'é', 'ó', 'ú']
    if any(char in text_lower for char in czech_indicators):
        return Language.CZECH

    # English indicators (common English words)
    english_indicators = ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']
    if any(word in text_lower for word in english_indicators):
        return Language.ENGLISH

    # Default to Russian
    return Language.RUSSIAN


def get_supported_languages() -> list[Language]:
    """Get list of supported languages."""
    return list(Language)
