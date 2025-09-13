"""Inline keyboards for the Vechnost bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .models import ContentType, Theme


def get_theme_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for theme selection."""
    keyboard = [
        [InlineKeyboardButton("🤝 Acquaintance", callback_data="theme_Acquaintance")],
        [InlineKeyboardButton("💕 For Couples", callback_data="theme_For Couples")],
        [InlineKeyboardButton("🔥 Sex", callback_data="theme_Sex")],
        [InlineKeyboardButton("⚡ Provocation", callback_data="theme_Provocation")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_level_keyboard(theme: Theme, available_levels: list[int]) -> InlineKeyboardMarkup:
    """Get keyboard for level selection."""
    keyboard = []
    for level in available_levels:
        button_text = f"Level {level}"
        if theme == Theme.SEX:
            button_text = f"🔥 Level {level}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"level_{level}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("← Back to Themes", callback_data="back_to_themes")])

    return InlineKeyboardMarkup(keyboard)


def get_content_type_keyboard(available_types: list[ContentType]) -> InlineKeyboardMarkup:
    """Get keyboard for content type selection (Sex theme only)."""
    keyboard = []

    if ContentType.QUESTIONS in available_types:
        keyboard.append([InlineKeyboardButton("❓ Questions", callback_data="content_questions")])

    if ContentType.TASKS in available_types:
        keyboard.append([InlineKeyboardButton("🎯 Tasks", callback_data="content_tasks")])

    # Add back button
    keyboard.append([InlineKeyboardButton("← Back to Levels", callback_data="back_to_levels")])

    return InlineKeyboardMarkup(keyboard)


def get_game_keyboard(remaining_cards: int) -> InlineKeyboardMarkup:
    """Get keyboard for game actions."""
    keyboard = []

    if remaining_cards > 0:
        keyboard.append([InlineKeyboardButton("🎲 Draw Next Card", callback_data="draw_card")])

    # Add toggle for Sex theme
    keyboard.append([InlineKeyboardButton("🔄 Switch Questions/Tasks", callback_data="toggle_content")])

    # Add reset button
    keyboard.append([InlineKeyboardButton("🔄 Reset Game", callback_data="reset_game")])

    return InlineKeyboardMarkup(keyboard)


def get_nsfw_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for NSFW content confirmation."""
    keyboard = [
        [
            InlineKeyboardButton("✅ I'm 18+", callback_data="nsfw_confirm"),
            InlineKeyboardButton("❌ I'm under 18", callback_data="nsfw_deny"),
        ],
        [InlineKeyboardButton("← Back to Themes", callback_data="back_to_themes")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for reset confirmation."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Reset", callback_data="reset_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="reset_cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
