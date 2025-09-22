"""Language selection keyboards for the Vechnost bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import Language, get_language_name, get_supported_languages


def get_language_selection_keyboard(current_language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Create language selection keyboard."""
    languages = get_supported_languages()
    keyboard = []

    # Create buttons for each language
    for i in range(0, len(languages), 2):
        row = []
        for j in range(2):
            if i + j < len(languages):
                lang = languages[i + j]
                # Use short language codes
                lang_codes = {
                    Language.RUSSIAN: "RU",
                    Language.ENGLISH: "EN",
                    Language.CZECH: "CZ"
                }
                lang_name = lang_codes[lang]
                # Add checkmark if it's the current language
                if lang == current_language:
                    lang_name = f"✓ {lang_name}"

                row.append(InlineKeyboardButton(
                    lang_name,
                    callback_data=f"lang_{lang.value}"
                ))
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def get_language_confirmation_keyboard(language: Language) -> InlineKeyboardMarkup:
    """Create language confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(
                "✓ Confirm",
                callback_data=f"lang_confirm_{language.value}"
            ),
            InlineKeyboardButton(
                "← Back",
                callback_data="lang_back"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)
