> **Archived.** A historical note, kept for the record and no longer maintained: the code has moved on since. The root README.md and CLAUDE.md describe the project as it is.

# Troubleshooting Payment Integration

## ✅ Что было добавлено

### 1. Информационный экран `/about`
- ✅ Команда `/about` на 3 языках (RU, EN, CS)
- ✅ Показывает полную информацию о боте, как на скриншоте ХЛБ
- ✅ Описание возможностей, инструкции, для кого подходит

### 2. Проверка оплаты после выбора языка
- ✅ После выбора языка бот проверяет статус оплаты
- ✅ Если `ENABLE_PAYMENT=TRUE` и у пользователя нет доступа - показывает экран оплаты
- ✅ Регистрирует пользователя в базе данных автоматически

## 🔍 Проверка настроек в Railway

### Проблема: "Бот не спрашивает об оплате"

**Причина**: Переменная `ENABLE_PAYMENT` не настроена правильно или установлена в `FALSE`

### ✅ Решение:

1. **Откройте Railway Dashboard** → Ваш проект → Variables

2. **Проверьте значение `ENABLE_PAYMENT`**:
   - ❌ **Неправильно**: пустое значение, `false`, `False`, `0`
   - ✅ **Правильно**: `TRUE`, `true`, `1`

3. **Установите правильное значение**:
   ```
   ENABLE_PAYMENT=TRUE
   ```
   или
   ```
   ENABLE_PAYMENT=true
   ```

4. **Важно**: После изменения переменной Railway автоматически перезапустит бот.

### Проверка других необходимых переменных для оплаты:

```
ENABLE_PAYMENT=TRUE                  # ✅ Должно быть TRUE
TRIBUTE_API_KEY=trib_xxxxx          # ✅ Ваш API ключ
WEBHOOK_SECRET=whsec_xxxxx          # ✅ Секрет для вебхуков
DATABASE_URL=sqlite:///./vechnost.db # ✅ Путь к БД
```

## 🧪 Как проверить что оплата работает

### Шаг 1: Проверьте переменные
```bash
# В логах Railway при запуске должно быть:
Application created with handlers:
- Command handlers: start, help, reset, about
```

### Шаг 2: Начните новую сессию с ботом
1. Отправьте `/start`
2. Выберите язык
3. **Должен появиться экран оплаты** с кнопками:
   - 💳 Купить доступ
   - 🔄 Проверить статус оплаты

### Шаг 3: Если экран оплаты НЕ появился
- Проверьте `ENABLE_PAYMENT=TRUE` в Railway
- Перезапустите бот в Railway
- Проверьте логи на ошибки

## 📝 Команды бота

После исправления будут доступны:
- `/start` - Начать игру (выбор языка)
- `/about` - **НОВОЕ** Информация о боте
- `/help` - Помощь
- `/reset` - Сбросить игру

## 🎯 Как должен работать флоу с оплатой

### С включенной оплатой (`ENABLE_PAYMENT=TRUE`):

1. Пользователь: `/start`
2. Бот: Выбор языка
3. Пользователь: Выбирает язык (RU)
4. **Бот: Проверяет оплату**
   - ❌ Нет оплаты → Экран "🔒 Требуется доступ"
   - ✅ Есть оплата → Приветственное сообщение
5. Пользователь: Нажимает "💳 Купить доступ"
6. Переходит к Tribute для оплаты
7. После оплаты → webhook → база данных обновляется
8. Пользователь: "🔄 Проверить статус оплаты"
9. Бот: "✅ Доступ предоставлен!"
10. Показывает выбор темы

### Без оплаты (`ENABLE_PAYMENT=FALSE`):

1. Пользователь: `/start`
2. Бот: Выбор языка
3. Пользователь: Выбирает язык
4. Бот: Сразу приветственное сообщение (без проверки)
5. Показывает выбор темы

## 🐛 Типичные ошибки

### Ошибка 1: "AttributeError: 'CallbackHandlerRegistry' object has no attribute 'register'"
- ✅ **Исправлено**: CheckPaymentHandler теперь добавляется в `__init__`

### Ошибка 2: "Бот не требует оплату"
- ❌ **Проблема**: `ENABLE_PAYMENT` не установлен в `TRUE`
- ✅ **Решение**: Установите `ENABLE_PAYMENT=TRUE` в Railway Variables

### Ошибка 3: "Webhook не работает"
- ❌ **Проблема**: Webhook server не запущен
- ✅ **Решение**:
  ```bash
  python run_webhook_server.py
  ```
  И настройте URL в Tribute Dashboard

## 📊 Проверка в базе данных

После первого входа пользователя, проверьте БД:

```python
# Локально:
sqlite3 vechnost.db
SELECT * FROM users;
```

Должна быть запись с `telegram_user_id` пользователя.

## 🚀 Быстрый чеклист

- [ ] `ENABLE_PAYMENT=TRUE` в Railway Variables
- [ ] `TRIBUTE_API_KEY` установлен и корректен
- [ ] `WEBHOOK_SECRET` установлен
- [ ] Бот перезапущен после изменения переменных
- [ ] Webhook server запущен (если используете локально)
- [ ] База данных инициализирована: `alembic upgrade head`
- [ ] Продукты синхронизированы: `python sync_products.py`

## 💡 Дополнительные команды для тестирования

```bash
# Проверить что модули импортируются
python -c "from vechnost_bot.payments.services import user_has_access; print('OK')"

# Проверить значение ENABLE_PAYMENT
python -c "from vechnost_bot.config import settings; print(f'ENABLE_PAYMENT={settings.enable_payment}')"

# Инициализировать БД
alembic upgrade head

# Синхронизировать продукты
python sync_products.py

# Запустить webhook server
python run_webhook_server.py
```

## 📞 Если ничего не помогает

1. Проверьте логи Railway на ошибки
2. Убедитесь что все зависимости установлены
3. Попробуйте пересоздать deployment в Railway
4. Проверьте что `aiosqlite` установлен для async SQLite

## ✨ Итого

После правильной настройки `ENABLE_PAYMENT=TRUE`:
- ✅ Пользователи без оплаты увидят экран "🔒 Требуется доступ"
- ✅ Команда `/about` покажет информацию о боте на 3 языках
- ✅ После оплаты через Tribute пользователи получат доступ
- ✅ Можно проверить статус через кнопку "🔄 Проверить статус оплаты"

