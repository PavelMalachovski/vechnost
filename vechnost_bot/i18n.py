"""Internationalization (i18n) support for the Vechnost bot."""

import logging
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from babel import Locale
from babel.support import Format

logger = logging.getLogger(__name__)


class Language(str, Enum):
    """The languages the product ships. English and Czech are retired: the
    content behind them is in git history, one revert away, but nothing at
    runtime branches on language any more."""
    RUSSIAN = "ru"

    @classmethod
    def coerce(cls, code: "str | Language | None") -> "Language":
        """A stored or client-supplied code, read as a supported language.

        Users predating this change carry `en`/`cs` in the database and in
        Mini App query strings; `Language(code)` would raise on those, and
        it is called on paths that render outside a try block.

        An already-typed member short-circuits: this is a `str, Enum`, so
        `str(Language.RUSSIAN)` is `"Language.RUSSIAN"` and a member would
        otherwise fall through to the fallback and come back as Russian by
        luck rather than by lookup.
        """
        if isinstance(code, cls):
            return code
        try:
            return cls(str(code).lower())
        except (ValueError, AttributeError):
            return cls.RUSSIAN


class I18nManager:
    """Manages internationalization for the bot."""

    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.translations: dict[Language, dict[str, Any]] = {}
        self.formatters: dict[Language, Format] = {}
        self._load_translations()
        self._setup_formatters()

    def _load_translations(self) -> None:
        """Load all translation files."""
        for language in Language:
            try:
                # Load UI translations
                ui_file = self.data_dir / f"translations_{language.value}.yaml"
                if ui_file.exists():
                    with open(ui_file, encoding='utf-8') as f:
                        ui_translations = yaml.safe_load(f) or {}
                else:
                    ui_translations = {}

                # Only the UI strings. This also read `questions_{lang}.yaml`
                # into a "questions" key for `get_questions`, but that file has
                # never existed under that name — the deck lives in
                # `data/questions.yaml` and is loaded by `logic.py` — so the
                # key was always empty, and its one reader is gone.
                self.translations[language] = {"ui": ui_translations}

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


# Global i18n manager instance
i18n_manager = I18nManager()


# Convenience functions
def get_text(key: str, language: Language = Language.RUSSIAN, **kwargs) -> str:
    """Get translated text for a key."""
    return i18n_manager.get_text(key, language, **kwargs)


def format_number(number: int, language: Language = Language.RUSSIAN) -> str:
    """Format a number according to locale rules."""
    return i18n_manager.format_number(number, language)


# `get_language_name`, `get_supported_languages` and `detect_language_from_text`
# lived here to feed the language chooser and the `/start` flow that picked a
# language from the user's message. Both of those callers are gone, and all
# three functions had collapsed to a constant — deleted rather than left as
# Russian-shaped stubs.
#
# `get_questions` and `get_available_themes` went the same way, and had never
# worked: the first read a "questions" key filled from a `questions_ru.yaml`
# that has never existed, the second a "themes" key `_load_translations` never
# wrote, so it always returned `{}`. Nothing imported either. The deck is
# `logic.py`'s (`data/questions.yaml`) and the theme names are ordinary
# `get_text('themes.…')` lookups.
