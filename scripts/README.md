# 🛠️ Scripts

Эта папка содержит вспомогательные Python скрипты для управления ботом.

## 📋 Список скриптов

### 🔧 Административные скрипты

- **`activate_user.py`** - Активация пользователя на N дней
- **`activate_simple.py`** - Упрощенная активация пользователя (поддержка lifetime)
- **`check_user_payment.py`** - Проверка статуса платежа пользователя
- **`check_user_simple.py`** - Простая проверка пользователя (без emoji)
- **`list_users.py`** - Список всех пользователей в БД

### 🗄️ Работа с базой данных

- **`check_local_db.py`** - Просмотр локальной SQLite базы
- **`check_railway_db.py`** - Просмотр Railway PostgreSQL базы
- **`migrate_to_lifetime.py`** - Миграция к поддержке lifetime подписок

### 🧪 Тестирование

- **`test_webhook.py`** - Интерактивный тестер webhook
- **`test_all_webhooks.py`** - Полный набор тестов webhook
- **`quick_test_webhook.py`** - Быстрый тест одного webhook

### 🚀 Запуск сервисов

- **`start_webhook_server.py`** - Запуск webhook сервера локально
- **`start_services.py`** - Запуск webhook сервера и бота (для Railway)
- **`run_webhook_server.py`** - Альтернативный запуск webhook сервера

### 🔄 Синхронизация

- **`sync_products.py`** - Синхронизация продуктов из Tribute API

## 📖 Использование

### Примеры запуска:

```bash
# Проверить пользователя
python scripts/check_user_simple.py 1115719673

# Активировать пользователя на 30 дней
python scripts/activate_user.py 1115719673 30

# Активировать lifetime подписку
python scripts/activate_simple.py 1115719673 lifetime

# Протестировать webhook
python scripts/quick_test_webhook.py

# Запустить webhook сервер локально
python scripts/start_webhook_server.py
```

### 🔗 Связанные файлы

- **`../sql/`** - SQL скрипты для работы с БД
- **`../docs/`** - Документация по использованию скриптов

## ⚠️ Важные заметки

1. **Переменные окружения**: Большинство скриптов требуют настройки `DATABASE_URL`
2. **Railway**: Для работы с Railway PostgreSQL используйте `railway shell` или настройте переменные
3. **Локальная разработка**: Используйте SQLite для локального тестирования
4. **Безопасность**: Не запускайте скрипты в production без проверки

## 📚 Документация

Подробная документация доступна в папке `../docs/`:
- `ADMIN_SCRIPTS.md` - Руководство по административным скриптам
- `WEBHOOK_TESTING.md` - Тестирование webhook
- `RAILWAY_WEBHOOK_SETUP.md` - Настройка на Railway
