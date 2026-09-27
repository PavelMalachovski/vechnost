> **Archived.** A historical note, kept for the record and no longer maintained: the code has moved on since. The root README.md and CLAUDE.md describe the project as it is.

# Payment Update Guide

## Что изменилось

1. ✅ Добавлен модуль `aiosqlite` для работы с базой данных
2. ✅ Добавлена приветственная страница после выбора языка
3. ✅ Проверка оплаты перенесена на кнопку "Начать игру"

## Новый флоу пользователя

```
/start
  → Выбор языка (🇷🇺 🇬🇧 🇨🇿)
  → Приветственная страница (с описанием игры)
  → Кнопка "🚀 Начать игру"
  → Проверка подписки:
     - Есть подписка → Выбор темы
     - Нет подписки → Редирект на Tribute
```

## Обновление на Railway

### Шаг 1: Проверьте переменные окружения

Убедитесь, что в вашем проекте на Railway установлены следующие переменные:

```bash
ENABLE_PAYMENT=True              # Включить проверку оплаты
TRIBUTE_API_KEY=your_api_key     # API ключ от Tribute
WEBHOOK_SECRET=your_secret       # Секрет для webhook
DATABASE_URL=sqlite+aiosqlite:///./vechnost.db  # БД (по умолчанию SQLite)
```

### Шаг 2: Задеплойте новую версию

```bash
git add .
git commit -m "Add greeting page and aiosqlite support"
git push origin main
```

Railway автоматически:
- Установит `aiosqlite` из `pyproject.toml`
- Пересоберёт Docker-образ
- Запустит обновленную версию бота

### Шаг 3: Проверьте работу

1. Откройте бота в Telegram
2. Нажмите `/start`
3. Выберите язык
4. Увидите приветственную страницу с описанием
5. Нажмите "🚀 Начать игру"
6. Если `ENABLE_PAYMENT=True` и нет подписки → увидите страницу оплаты

## Отключение оплаты (для тестирования)

Если хотите протестировать бота без оплаты:

```bash
ENABLE_PAYMENT=False
```

Тогда после нажатия "Начать игру" сразу откроется выбор тем.

## Устранение проблем

### Ошибка "No module named 'aiosqlite'"

**Причина**: Старая версия зависимостей.

**Решение**:
- Railway автоматически установит новые зависимости при деплое
- Если проблема сохраняется, в настройках Railway:
  1. Settings → Deploy Trigger → Manual Deploy
  2. Выберите "Redeploy"

### Бот не показывает приветственную страницу

**Причина**: Старая версия кода.

**Решение**:
1. Убедитесь, что вы сделали `git push`
2. Проверьте логи в Railway: Deployments → Latest → View Logs
3. Найдите строку `Application created with handlers: start, help, reset, about`

## Проверка логов

В Railway → Deployments → View Logs ищите:

✅ Успешный запуск:
```
Application created with handlers: start, help, reset, about
Starting Vechnost bot...
Application started
```

❌ Проблема с aiosqlite:
```
ModuleNotFoundError: No module named 'aiosqlite'
```
→ Триггер переразвёртывания (Redeploy)

## Структура приветственной страницы

### Русский
```
💎 Добро пожаловать в VECHNOST

Игра для пар, которая поможет вам:
• По-настоящему узнать друг друга
• Выйти за рамки обычных разговоров
• Открыть новые стороны себя и партнера

✨ 4 уникальные темы:
🤝 Знакомство — для первых встреч
💕 Для пар — углубление близости
🔥 Секс — интимные вопросы и задания
⚡ Провокации — неожиданные вопросы

💡 Что вас ждёт:
• Сотни тщательно подобранных вопросов
• 3 уровня сложности
• Приватность — всё остаётся между вами
• Поддержка 3 языков

🎮 Готовы начать?
Нажмите кнопку ниже!

[🚀 Начать игру]
```

Аналогичные тексты на английском и чешском.

## Техническая информация

### Новые файлы
- `vechnost_bot/callback_handlers.py` — добавлен `StartGameHandler`
- `data/translations_*.yaml` — добавлены ключи `welcome.greeting_*`

### Изменённые файлы
- `pyproject.toml` — добавлен `aiosqlite>=0.19.0`
- `vechnost_bot/callback_models.py` — добавлен `START_GAME` action
- `vechnost_bot/callback_handlers.py` — изменён `LanguageHandler`

### База данных
Используется SQLite с async драйвером `aiosqlite`.
Файл БД: `vechnost.db` (создаётся автоматически)

## Поддержка

Если возникли проблемы:
1. Проверьте логи Railway
2. Убедитесь, что все переменные окружения установлены
3. Проверьте версию Python (должна быть 3.11)
4. Попробуйте Redeploy в Railway

