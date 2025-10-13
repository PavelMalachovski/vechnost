# ⚡ Активировать пользователя 1115719673 ПРЯМО СЕЙЧАС

## Шаг 1: Переключитесь на БД

```bash
railway service
```

Выберите **vechnost-db** (стрелками ↑↓ и Enter)

---

## Шаг 2: Подключитесь к PostgreSQL

```bash
railway connect
```

Откроется `psql` консоль.

---

## Шаг 3: Скопируйте и вставьте этот SQL

```sql
INSERT INTO users (telegram_user_id, username, first_name, last_name, created_at)
VALUES (1115719673, NULL, 'User', NULL, NOW())
ON CONFLICT (telegram_user_id) DO NOTHING;

INSERT INTO subscriptions (user_id, tribute_subscription_id, status, start_date, end_date, created_at)
SELECT id, 'manual_1115719673_' || EXTRACT(EPOCH FROM NOW())::bigint, 'active', NOW(), NOW() + INTERVAL '30 days', NOW()
FROM users WHERE telegram_user_id = 1115719673;

SELECT u.telegram_user_id, s.status, s.start_date, s.end_date FROM users u LEFT JOIN subscriptions s ON s.user_id = u.id WHERE u.telegram_user_id = 1115719673;
```

Нажмите Enter.

---

## Шаг 4: Проверьте результат

Должно показать:
```
 telegram_user_id |  status  |       start_date        |        end_date
------------------+----------+-------------------------+-------------------------
       1115719673 | active   | 2025-10-13 19:55:00     | 2025-11-12 19:55:00
```

---

## Шаг 5: Выйдите из psql

```
\q
```

---

## ✅ Готово!

Теперь попросите пользователя:
1. Открыть бота
2. Нажать "🔄 Проверить статус оплаты"
3. Должно появиться: "✅ Доступ подтверждён!"

---

## 🎯 Или через Railway UI (ещё проще):

1. Откройте https://railway.app
2. Проект → **vechnost-db**
3. Вкладка **Data**
4. Нажмите **Query** (кнопка SQL запроса)
5. Вставьте SQL выше
6. Нажмите **Run**

---

**Время выполнения: 1 минута** ⏱️

