# 🔑 Активация пользователя через Railway

## Проблема
Скрипты активации не работают локально, так как `postgres.railway.internal` недоступен снаружи.

## ✅ Решение: Активация через Railway Connect

### Шаг 1: Подключитесь к PostgreSQL

В командной строке:
```bash
railway connect postgres
```

Это откроет `psql` клиент, подключенный к вашей БД.

### Шаг 2: Выполните SQL запрос

```sql
-- Активация пользователя 1115719673 на 30 дней

-- 1. Убедитесь, что пользователь существует
INSERT INTO users (telegram_user_id, username, first_name, last_name, created_at)
VALUES (1115719673, NULL, 'User', NULL, NOW())
ON CONFLICT (telegram_user_id) DO NOTHING;

-- 2. Создайте подписку
INSERT INTO subscriptions (
    user_id,
    tribute_subscription_id,
    status,
    start_date,
    end_date,
    created_at
)
SELECT
    id,
    'manual_1115719673_' || EXTRACT(EPOCH FROM NOW())::bigint,
    'active',
    NOW(),
    NOW() + INTERVAL '30 days',
    NOW()
FROM users
WHERE telegram_user_id = 1115719673;

-- 3. Проверьте результат
SELECT
    u.telegram_user_id,
    s.status,
    s.start_date,
    s.end_date
FROM users u
LEFT JOIN subscriptions s ON s.user_id = u.id
WHERE u.telegram_user_id = 1115719673;
```

### Шаг 3: Проверьте в боте

Попросите пользователя:
1. Открыть бота
2. Нажать "🔄 Проверить статус оплаты"
3. Должно появиться: "✅ Доступ подтверждён!"

---

## 🔄 Альтернатива: Railway UI

Если `railway connect` не работает:

1. Откройте **Railway.app** в браузере
2. Перейдите в **vechnost-db → Data**
3. Нажмите **Query** (кнопка запроса)
4. Вставьте SQL запрос выше
5. Нажмите **Run**

---

## 📝 Активация других пользователей

Замените `1115719673` на нужный Telegram ID:

```sql
-- Для пользователя 123456789 на 7 дней
INSERT INTO subscriptions (user_id, tribute_subscription_id, status, start_date, end_date, created_at)
SELECT
    id,
    'manual_123456789_' || EXTRACT(EPOCH FROM NOW())::bigint,
    'active',
    NOW(),
    NOW() + INTERVAL '7 days',
    NOW()
FROM users
WHERE telegram_user_id = 123456789;
```

Замените `7 days` на:
- `1 day` - 1 день
- `7 days` - неделя
- `30 days` - месяц
- `365 days` - год

---

## ✅ Проверка активации

```sql
-- Посмотреть всех пользователей с подписками
SELECT
    u.telegram_user_id,
    u.first_name,
    s.status,
    s.start_date,
    s.end_date,
    EXTRACT(DAY FROM (s.end_date - NOW())) as days_left
FROM users u
LEFT JOIN subscriptions s ON s.user_id = u.id
ORDER BY u.created_at DESC;
```

---

## 🎯 Полезные SQL команды

### Посмотреть всех пользователей:
```sql
SELECT * FROM users ORDER BY created_at DESC LIMIT 10;
```

### Посмотреть все подписки:
```sql
SELECT * FROM subscriptions ORDER BY created_at DESC LIMIT 10;
```

### Деактивировать подписку:
```sql
UPDATE subscriptions
SET status = 'cancelled', end_date = NOW()
WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = 1115719673);
```

### Продлить подписку на 30 дней:
```sql
UPDATE subscriptions
SET end_date = end_date + INTERVAL '30 days'
WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = 1115719673)
AND status = 'active';
```

