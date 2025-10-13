# 🗄️ SQL Scripts

Эта папка содержит SQL скрипты для работы с базой данных.

## 📋 Список файлов

### 🔧 Активация пользователей

- **`activate_via_sql.sql`** - SQL скрипт для активации пользователя напрямую через БД

### 🔄 Миграции

- **`update_to_lifetime.sql`** - SQL для обновления подписки на lifetime

## 📖 Использование

### Через Railway CLI:

```bash
# Подключиться к PostgreSQL
railway connect postgres

# Выполнить скрипт
\i sql/activate_via_sql.sql
```

### Через Railway UI:

1. Откройте Railway Dashboard
2. Перейдите в PostgreSQL сервис
3. Откройте Query (SQL консоль)
4. Скопируйте и выполните нужный SQL

### Примеры использования:

#### Активация пользователя на 30 дней:
```sql
-- Из activate_via_sql.sql
INSERT INTO subscriptions (user_id, subscription_id, period, status, expires_at, last_event_at)
SELECT
    u.id,
    12345,
    '30d',
    'active',
    NOW() + INTERVAL '30 days',
    NOW()
FROM users u
WHERE u.telegram_user_id = 1115719673;
```

#### Создание lifetime подписки:
```sql
-- Из update_to_lifetime.sql
UPDATE subscriptions
SET expires_at = NULL, period = 'lifetime'
WHERE user_id IN (
    SELECT id FROM users WHERE telegram_user_id = 1115719673
) AND status = 'active';
```

## ⚠️ Важные заметки

1. **Бэкап**: Всегда делайте бэкап БД перед выполнением SQL
2. **Проверка**: Проверяйте результат после выполнения скриптов
3. **Безопасность**: Не выполняйте SQL в production без тестирования
4. **Идемпотентность**: Скрипты можно запускать несколько раз

## 🔗 Связанные файлы

- **`../scripts/`** - Python скрипты для работы с БД
- **`../docs/`** - Документация по работе с БД
