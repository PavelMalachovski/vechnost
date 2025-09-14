"""Inline keyboards for the Vechnost bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import t
from .models import ContentType, Theme


def get_theme_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for theme selection."""
    keyboard = [
        [InlineKeyboardButton(f"🤝 {t(chat_id, 'ui.topic_acq')}", callback_data="theme_Acquaintance")],
        [InlineKeyboardButton(f"💕 {t(chat_id, 'ui.topic_couples')}", callback_data="theme_For Couples")],
        [InlineKeyboardButton(f"🔥 {t(chat_id, 'ui.topic_sex')}", callback_data="theme_Sex")],
        [InlineKeyboardButton(f"⚡ {t(chat_id, 'ui.topic_prov')}", callback_data="theme_Provocation")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_level_keyboard(theme: Theme, available_levels: list[int], chat_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for level selection."""
    keyboard = []

    level_texts = {1: t(chat_id, 'ui.level_1'), 2: t(chat_id, 'ui.level_2'), 3: t(chat_id, 'ui.level_3')}

    for level in available_levels:
        button_text = level_texts.get(level, f"{t(chat_id, 'ui.level_1')} {level}")
        if theme == Theme.SEX:
            button_text = f"🔥 {button_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"level_{level}")])

    # Add back button
    keyboard.append([InlineKeyboardButton(f"← {t(chat_id, 'ui.back_topics')}", callback_data="back:themes")])

    return InlineKeyboardMarkup(keyboard)


def get_calendar_keyboard(
    topic: str,
    level_or_0: int,
    category: str,
    page: int,
    items: list[str],
    total_pages: int,
    show_toggle: bool = False
) -> InlineKeyboardMarkup:
    """
    Build calendar-style keyboard with 7 columns, 4 rows (28 items per page).

    Args:
        topic: Topic code (acq, couples, sex, prov)
        level_or_0: Level number or 0 if no levels
        category: 'q' for questions, 't' for tasks
        page: Current page (0-based)
        items: List of all items for this topic/level/category
        total_pages: Total number of pages
        show_toggle: Whether to show Sex toggle button
    """
    keyboard = []

    # Calculate start and end indices for current page
    items_per_page = 28  # 4 rows × 7 columns
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(items))
    page_items = items[start_idx:end_idx]

    # Add toggle button for Sex theme (only for Sex)
    if show_toggle:
        toggle_text = SEX_TOGGLE
        other_category = 't' if category == 'q' else 'q'
        keyboard.append([InlineKeyboardButton(
            toggle_text,
            callback_data=f"toggle:sex:{other_category}:{page}"
        )])

    # Build calendar grid (4 rows × 7 columns)
    for row in range(4):
        row_start = row * 7
        row_end = min(row_start + 7, len(page_items))
        if row_start < len(page_items):
            row_buttons = []
            for i in range(row_start, row_end):
                item_idx = start_idx + i
                button_text = str(item_idx + 1)  # 1-based numbering
                row_buttons.append(InlineKeyboardButton(
                    button_text,
                    callback_data=f"q:{topic}:{level_or_0}:{item_idx}"
                ))
            keyboard.append(row_buttons)

    # Add pagination row
    if total_pages > 1:
        pagination_buttons = []

        # Previous page button
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(
                PREV_PAGE,
                callback_data=f"cal:{topic}:{level_or_0}:{category}:{page-1}"
            ))
        else:
            pagination_buttons.append(InlineKeyboardButton(" ", callback_data="noop"))

        # Page indicator
        page_text = PAGE_FORMAT.format(current=page+1, total=total_pages)
        pagination_buttons.append(InlineKeyboardButton(page_text, callback_data="noop"))

        # Next page button
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton(
                NEXT_PAGE,
                callback_data=f"cal:{topic}:{level_or_0}:{category}:{page+1}"
            ))
        else:
            pagination_buttons.append(InlineKeyboardButton(" ", callback_data="noop"))

        keyboard.append(pagination_buttons)

    # Add back button
    if level_or_0 == 0:
        # No levels, go back to themes
        keyboard.append([InlineKeyboardButton(f"← {BACK_TO_THEMES}", callback_data="back:themes")])
    else:
        # Has levels, go back to level selection
        keyboard.append([InlineKeyboardButton(f"← {BACK_TO_LEVELS}", callback_data="back:levels")])

    return InlineKeyboardMarkup(keyboard)


def get_question_keyboard(
    topic: str,
    level_or_0: int,
    current_index: int,
    total_items: int
) -> InlineKeyboardMarkup:
    """
    Get keyboard for displaying a question with navigation.

    Args:
        topic: Topic code (acq, couples, sex, prov)
        level_or_0: Level number or 0 if no levels
        current_index: Current question index (0-based)
        total_items: Total number of items in this category
    """
    keyboard = []

    # Navigation row
    nav_buttons = []

    # Previous question button
    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton(
            PREV_QUESTION,
            callback_data=f"nav:{topic}:{level_or_0}:{current_index-1}"
        ))
    else:
        nav_buttons.append(InlineKeyboardButton(" ", callback_data="noop"))

    # Next question button
    if current_index < total_items - 1:
        nav_buttons.append(InlineKeyboardButton(
            NEXT_QUESTION,
            callback_data=f"nav:{topic}:{level_or_0}:{current_index+1}"
        ))
    else:
        nav_buttons.append(InlineKeyboardButton(" ", callback_data="noop"))

    keyboard.append(nav_buttons)

    # Back button
    keyboard.append([InlineKeyboardButton(f"← {BACK}", callback_data="back:calendar")])

    return InlineKeyboardMarkup(keyboard)


def get_nsfw_confirmation_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for NSFW content confirmation."""
    keyboard = [
        [
            InlineKeyboardButton(t(chat_id, 'ui.nsfw_confirm'), callback_data="nsfw_confirm"),
            InlineKeyboardButton(t(chat_id, 'ui.nsfw_deny'), callback_data="nsfw_deny"),
        ],
        [InlineKeyboardButton(f"← {t(chat_id, 'ui.back_topics')}", callback_data="back:themes")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for reset confirmation."""
    from .i18n import RESET_YES, RESET_CANCEL

    keyboard = [
        [
            InlineKeyboardButton(RESET_YES, callback_data="reset_confirm"),
            InlineKeyboardButton(RESET_CANCEL, callback_data="reset_cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
