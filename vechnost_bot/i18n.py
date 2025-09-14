"""Internationalization support for Vechnost bot."""

import os
import sqlite3
import yaml
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, Optional

# Database path
DB_PATH = Path(__file__).parent.parent / "user_languages.db"

# Supported languages
SUPPORTED_LANGUAGES = {"ru", "en", "cs"}
DEFAULT_LANGUAGE = "en"

# Language code mapping
LANGUAGE_CODE_MAP = {
    "ru": "ru",
    "en": "en",
    "cs": "cs",
    "uk": "ru",  # Ukrainian -> Russian
    "be": "ru",  # Belarusian -> Russian
    "bg": "ru",  # Bulgarian -> Russian
    "sk": "cs",  # Slovak -> Czech
    "pl": "cs",  # Polish -> Czech
}

# Cache for loaded data
_LOCALES_CACHE: Dict[str, Dict[str, Any]] = {}
_CONTENT_CACHE: Dict[str, Dict[str, Any]] = {}


def init_database() -> None:
    """Initialize the SQLite database for user language preferences."""
    DB_PATH.parent.mkdir(exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_lang (
                chat_id TEXT PRIMARY KEY,
                lang TEXT NOT NULL
            )
        """)
        conn.commit()


def get_lang(chat_id: int) -> str:
    """Get user's preferred language."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT lang FROM user_lang WHERE chat_id = ?",
                (str(chat_id),)
            )
            result = cursor.fetchone()
            return result[0] if result else DEFAULT_LANGUAGE
    except Exception:
        return DEFAULT_LANGUAGE


def set_lang(chat_id: int, lang: str) -> None:
    """Set user's preferred language."""
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_lang (chat_id, lang) VALUES (?, ?)",
                (str(chat_id), lang)
            )
            conn.commit()
    except Exception:
        pass  # Fail silently


def detect_language_from_code(language_code: Optional[str]) -> str:
    """Detect best language from Telegram language code."""
    if not language_code:
        return DEFAULT_LANGUAGE

    # Try exact match first
    if language_code in SUPPORTED_LANGUAGES:
        return language_code

    # Try mapping
    return LANGUAGE_CODE_MAP.get(language_code, DEFAULT_LANGUAGE)


@lru_cache(maxsize=32)
def _load_locale(lang: str) -> Dict[str, Any]:
    """Load and cache locale file."""
    if lang in _LOCALES_CACHE:
        return _LOCALES_CACHE[lang]

    locale_path = Path(__file__).parent.parent / "locales" / f"{lang}.yml"

    try:
        with open(locale_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            _LOCALES_CACHE[lang] = data
            return data
    except Exception:
        # Fallback to English
        if lang != "en":
            return _load_locale("en")
        return {}


@lru_cache(maxsize=32)
def _load_content(lang: str) -> Dict[str, Any]:
    """Load and cache content file."""
    if lang in _CONTENT_CACHE:
        return _CONTENT_CACHE[lang]

    content_path = Path(__file__).parent.parent / "content" / f"{lang}.yml"

    try:
        with open(content_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            _CONTENT_CACHE[lang] = data
            return data
    except Exception:
        # Fallback to Russian (original)
        if lang != "ru":
            return _load_content("ru")
        return {}


def t(chat_id: int, key: str, **kwargs) -> str:
    """Translate a UI string for the given chat."""
    lang = get_lang(chat_id)
    locale_data = _load_locale(lang)

    # Navigate through nested keys (e.g., "ui.welcome_title")
    keys = key.split('.')
    value = locale_data

    try:
        for k in keys:
            value = value[k]

        # Format with kwargs if provided
        if kwargs:
            return value.format(**kwargs)
        return value
    except (KeyError, TypeError):
        # Fallback to English
        if lang != "en":
            return t(chat_id, key, **kwargs) if lang != "en" else key
        return key


def get_content(lang: str) -> Dict[str, Any]:
    """Get content for a specific language."""
    return _load_content(lang)


def get_ui_string(chat_id: int, key: str, **kwargs) -> str:
    """Get a UI string for the given chat (alias for t)."""
    return t(chat_id, key, **kwargs)


def clear_cache() -> None:
    """Clear all caches (useful for testing)."""
    global _LOCALES_CACHE, _CONTENT_CACHE
    _LOCALES_CACHE.clear()
    _CONTENT_CACHE.clear()
    _load_locale.cache_clear()
    _load_content.cache_clear()


# Initialize database on import
init_database()
