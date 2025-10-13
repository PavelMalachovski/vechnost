# ✅ Чеклист для деплоя обновления

## Что было сделано

### 1. ✅ Исправлена ошибка с `aiosqlite`
- Добавлен `aiosqlite>=0.19.0` в `pyproject.toml`
- Это устранит ошибку `ModuleNotFoundError: No module named 'aiosqlite'`
- **Таблицы БД создаются автоматически** при первом запуске (не нужно вручную запускать миграции)

### 2. ✅ Добавлена приветственная страница
- Показывается после выбора языка
- Красивое описание игры на всех 3 языках (RU, EN, CS)
- Кнопка "🚀 Начать игру"

### 3. ✅ Изменён флоу оплаты
**Старый:**
```
/start → Язык → Сразу проверка оплаты
```

**Новый:**
```
/start → Язык → Приветственная страница →
→ Кнопка "Начать игру" → Проверка оплаты →
→ Темы (если есть подписка) ИЛИ Tribute (если нет)
```

## Что нужно сделать на Railway

### Шаг 1: Проверьте переменные
В Railway → Variables убедитесь:
```bash
ENABLE_PAYMENT=True   # ← Измените на True (сейчас False)
TRIBUTE_API_KEY=xxx   # ← Ваш API ключ
WEBHOOK_SECRET=xxx    # ← Ваш секрет
DATABASE_URL=sqlite+aiosqlite:///./vechnost.db
```

### Шаг 2: Задеплойте
```bash
git add .
git commit -m "Add greeting page and fix aiosqlite"
git push origin main
```

Railway автоматически:
1. Установит новую зависимость `aiosqlite`
2. Пересоберёт Docker-образ
3. Запустит обновлённого бота

### Шаг 3: Тестирование

#### В Telegram боте:
1. `/start`
2. Выберите язык 🇷🇺
3. Увидите приветственную страницу с описанием
4. Нажмите "🚀 Начать игру"
5. **Если ENABLE_PAYMENT=True и нет подписки:**
   - Увидите сообщение об оплате
   - Кнопки "💳 Оформить подписку" и "🔄 Проверить оплату"
6. **Если ENABLE_PAYMENT=False или есть подписка:**
   - Сразу откроется выбор тем

## Ожидаемые логи (Railway)

✅ **Успешный запуск:**
```
Starting Container
Redis auto-started successfully
Application created with handlers: start, help, reset, about
Starting Vechnost bot...
Application started
```

✅ **После выбора языка (без aiosqlite ошибки):**
```
Callback query received: lang_ru from chat 1115719673
# Больше НЕ должно быть: "Error registering user: No module named 'aiosqlite'"
```

✅ **После нажатия "Начать игру" (первый запуск):**
```
Callback query received: start_game from chat 1115719673
Initializing database with URL: sqlite+aiosqlite:///./vechnost.db
Database initialized successfully
Database tables created successfully  # ← Таблицы создались автоматически!
# Проверка подписки...
```

## Возможные проблемы

### ❌ Всё ещё "No module named 'aiosqlite'"
**Решение:** Railway → Settings → Redeploy

### ❌ "no such table: users"
**Причина:** Старая версия кода без автосоздания таблиц
**Решение:**
1. Убедитесь, что задеплоили новую версию с обновлённым `database.py`
2. Перезапустите бот в Railway (Redeploy)
3. Таблицы создадутся автоматически при первом запуске

### ❌ Не показывает приветственную страницу
**Решение:**
1. Убедитесь, что код задеплоен: `git push origin main`
2. Проверьте логи: есть ли строка `Application created with handlers: start, help, reset, about`

### ❌ Не проверяет оплату
**Причина:** `ENABLE_PAYMENT=False` в Railway
**Решение:** Измените на `ENABLE_PAYMENT=True` в Variables

## Файлы для проверки

После деплоя эти файлы должны быть обновлены:
- ✅ `pyproject.toml` — содержит `aiosqlite>=0.19.0`
- ✅ `vechnost_bot/callback_handlers.py` — есть `StartGameHandler`
- ✅ `vechnost_bot/callback_models.py` — есть `START_GAME`
- ✅ `data/translations_ru.yaml` — есть `greeting_title`, `greeting_intro` и т.д.
- ✅ `data/translations_en.yaml` — аналогично
- ✅ `data/translations_cs.yaml` — аналогично

## Контакты для вопросов

Документация:
- `docs/PAYMENT_UPDATE_GUIDE.md` — полное руководство
- `docs/ENVIRONMENT_VARIABLES.md` — все переменные окружения
- `docs/PAYMENT_TROUBLESHOOTING.md` — решение проблем с оплатой

---

**Готово к деплою! 🚀**

