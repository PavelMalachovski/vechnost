"""Inline keyboards for the Vechnost bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import Language, get_text, get_language_name, get_supported_languages
from .language_keyboards import get_language_selection_keyboard
from .models import ContentType, Theme


def get_theme_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for theme selection."""
    keyboard = [
        [InlineKeyboardButton(
            get_text('themes.Acquaintance', language),
            callback_data="theme_Acquaintance"
        )],
        [InlineKeyboardButton(
            get_text('themes.For Couples', language),
            callback_data="theme_For Couples"
        )],
        [InlineKeyboardButton(
            get_text('themes.Sex', language),
            callback_data="theme_Sex"
        )],
        [InlineKeyboardButton(
            get_text('themes.Provocation', language),
            callback_data="theme_Provocation"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_level_keyboard(theme: Theme, available_levels: list[int], language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for level selection."""
    keyboard = []

    for level in available_levels:
        button_text = f"{get_text('level.level', language)} {level}"
        if theme == Theme.SEX:
            button_text = f"🔥 {button_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"level_{level}")])

    # Add back button
    keyboard.append([InlineKeyboardButton(
        get_text('navigation.back', language),
        callback_data="back:themes"
    )])

    return InlineKeyboardMarkup(keyboard)


def get_calendar_keyboard(
    topic_code: str,
    level_or_0: int,
    category: str,
    page: int,
    items: list,
    total_pages: int,
    show_toggle: bool = False,
    language: Language = Language.RUSSIAN
) -> InlineKeyboardMarkup:
    """Get keyboard for calendar navigation."""
    keyboard = []
    items_per_page = 28
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(items))

    # Create calendar grid (7x4 = 28 items)
    for row in range(4):
        keyboard_row = []
        for col in range(7):
            item_idx = start_idx + row * 7 + col
            if item_idx < end_idx:
                day_num = item_idx + 1
                keyboard_row.append(InlineKeyboardButton(
                    str(day_num),
                    callback_data=f"q:{topic_code}:{level_or_0}:{item_idx}"
                ))
            else:
                keyboard_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        keyboard.append(keyboard_row)

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            f"← {get_text('navigation.previous', language)}",
            callback_data=f"cal:{topic_code}:{level_or_0}:{category}:{page-1}"
        ))

    nav_row.append(InlineKeyboardButton(
        f"{get_text('navigation.page', language).format(current=page+1, total=total_pages)}",
        callback_data="noop"
    ))

    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(
            get_text('navigation.next', language),
            callback_data=f"cal:{topic_code}:{level_or_0}:{category}:{page+1}"
        ))

    keyboard.append(nav_row)

    # Toggle row (only for Sex theme)
    if show_toggle:
        toggle_row = []
        if category == "q":
            toggle_row.append(InlineKeyboardButton(
                f"📝 {get_text('navigation.toggle_tasks', language)}",
                callback_data=f"toggle:sex:0:t"
            ))
        else:
            toggle_row.append(InlineKeyboardButton(
                f"❓ {get_text('navigation.toggle_questions', language)}",
                callback_data=f"toggle:sex:0:q"
            ))
        keyboard.append(toggle_row)

    # Back button
    keyboard.append([InlineKeyboardButton(
        get_text('navigation.back', language),
        callback_data="back:levels"
    )])

    return InlineKeyboardMarkup(keyboard)


def get_question_keyboard(
    topic_code: str,
    level_or_0: int,
    question_idx: int,
    total_questions: int,
    language: Language = Language.RUSSIAN
) -> InlineKeyboardMarkup:
    """Get keyboard for question navigation."""
    keyboard = []

    # Navigation row
    nav_row = []
    if question_idx > 0:
        nav_row.append(InlineKeyboardButton(
            get_text('navigation.previous', language),
            callback_data=f"nav:{topic_code}:{level_or_0}:{question_idx-1}"
        ))

    nav_row.append(InlineKeyboardButton(
        f"{get_text('question.header', language).format(current=question_idx+1, total=total_questions)}",
        callback_data="noop"
    ))

    if question_idx < total_questions - 1:
        nav_row.append(InlineKeyboardButton(
            get_text('navigation.next', language),
            callback_data=f"nav:{topic_code}:{level_or_0}:{question_idx+1}"
        ))

    keyboard.append(nav_row)

    # Back button
    keyboard.append([InlineKeyboardButton(
        get_text('navigation.back', language),
        callback_data="back:calendar"
    )])

    return InlineKeyboardMarkup(keyboard)


def get_nsfw_confirmation_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for NSFW content confirmation."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ {get_text('nsfw.confirm', language)}",
                callback_data="nsfw_confirm"
            ),
            InlineKeyboardButton(
                f"❌ {get_text('nsfw.deny', language)}",
                callback_data="nsfw_deny"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reset_confirmation_keyboard(language: Language = Language.RUSSIAN) -> InlineKeyboardMarkup:
    """Get keyboard for reset confirmation."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ {get_text('reset.confirm', language)}",
                callback_data="reset_confirm"
            ),
            InlineKeyboardButton(
                f"❌ {get_text('reset.cancel', language)}",
                callback_data="reset_cancel"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
