"""Russian translations for the Vechnost bot."""

# Start/welcome messages
WELCOME_TITLE = "Добро пожаловать в Vechnost!"
WELCOME_SUBTITLE = "Это интимная карточная игра, созданная для углубления отношений через содержательные разговоры."
WELCOME_PROMPT = "Выберите тему, чтобы начать:"

# Topics
TOPIC_ACQUAINTANCE = "Знакомство"
TOPIC_FOR_COUPLES = "Для пар"
TOPIC_SEX = "Секс"
TOPIC_PROVOCATION = "Провокация"

# Level selection
LEVEL_PROMPT = "Выберите уровень"
LEVEL_1 = "Уровень 1"
LEVEL_2 = "Уровень 2"
LEVEL_3 = "Уровень 3"

# Calendar
CALENDAR_HEADER = "Календарь вопросов"
CALENDAR_SEX_QUESTIONS = "Секс — вопросы"
CALENDAR_SEX_TASKS = "Секс — задания"

# Navigation buttons
BACK = "Назад"
BACK_TO_THEMES = "Назад к темам"
BACK_TO_LEVELS = "Назад к уровням"
PREV_PAGE = "←"
NEXT_PAGE = "→"
PREV_QUESTION = "←"
NEXT_QUESTION = "→"

# Sex toggle (only in Sex theme)
SEX_TOGGLE = "Вопросы ↔ Задания"

# Pager
PAGE_FORMAT = "Стр. {current}/{total}"

# Question display
QUESTION_HEADER = "Вопрос {current} из {total}"

# Error messages
ERROR_INVALID_THEME = "❌ Неверная тема."
ERROR_INVALID_LEVEL = "❌ Неверный уровень."
ERROR_INVALID_CONTENT_TYPE = "❌ Неверный тип контента."
ERROR_NO_THEME = "❌ Тема не выбрана."
ERROR_NO_LEVEL = "❌ Уровень не выбран."
ERROR_NO_CONTENT = "❌ Контент недоступен."
ERROR_UNKNOWN_CALLBACK = "❌ Неизвестная команда."

# NSFW content
NSFW_WARNING_TITLE = "⚠️ Предупреждение о контенте 18+"
NSFW_WARNING_TEXT = (
    "Тема 'Секс' содержит контент для взрослых, включая откровенные вопросы и задания. "
    "Вам должно быть 18 лет или больше для доступа к этому контенту.\n\n"
    "Вам есть 18 лет?"
)
NSFW_CONFIRM = "✅ Мне есть 18"
NSFW_DENY = "❌ Мне нет 18"
NSFW_ACCESS_DENIED = (
    "❌ Доступ запрещён\n\n"
    "Вам должно быть 18 лет или больше для доступа к контенту 18+. "
    "Пожалуйста, выберите другую тему."
)

# Help text
HELP_TITLE = "🎴 Помощь Vechnost"
HELP_THEMES = (
    "**Темы:**\n"
    "• 🤝 Знакомство - Узнайте друг друга лучше\n"
    "• 💕 Для пар - Углубите ваши отношения\n"
    "• 🔥 Секс - Интимные вопросы и задания (18+)\n"
    "• ⚡ Провокация - Сложные сценарии\n\n"
)
HELP_HOW_TO_PLAY = (
    "**Как играть:**\n"
    "1. Выберите тему\n"
    "2. Выберите уровень (если применимо)\n"
    "3. Выберите вопрос из календаря\n"
    "4. Обсудите ответы вместе\n\n"
)
HELP_COMMANDS = (
    "**Команды:**\n"
    "• /start - Начать новую игру\n"
    "• /help - Показать эту справку\n"
    "• /reset - Сбросить текущую игру\n\n"
    "Наслаждайтесь интимными разговорами! 💕"
)

# Reset
RESET_TITLE = "🔄 Сброс игры"
RESET_CONFIRM_TEXT = (
    "Вы уверены, что хотите сбросить текущую игру? "
    "Это очистит ваш прогресс и начнёт заново."
)
RESET_YES = "✅ Да, сбросить"
RESET_CANCEL = "❌ Отмена"
RESET_COMPLETED = "🔄 Игра сброшена\n\nВаша игра была сброшена. Выберите тему для начала новой игры:"
RESET_CANCELLED = "❌ Сброс отменён.\n\nВаша игра продолжается как прежде."
