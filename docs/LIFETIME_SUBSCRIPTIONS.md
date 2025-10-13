# ♾️ Вечные подписки (Lifetime Subscriptions)

## Что изменилось

Теперь подписки могут быть **вечными** (не истекают никогда).

### Как это работает:

- **`expires_at = NULL`** → Вечная подписка
- **`expires_at = дата`** → Подписка истекает в указанную дату
- **`period = 'lifetime'`** → Маркер вечной подписки

## 🔧 Изменения в коде

### 1. Модель (models.py)
```python
expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # NULL = lifetime

@property
def is_lifetime(self) -> bool:
    """Check if subscription is lifetime."""
    return self.expires_at is None
```

### 2. Репозиторий (repositories.py)
```python
.where(
    (Subscription.expires_at.is_(None)) |  # Lifetime
    (Subscription.expires_at > now)        # Or not expired
)
```

### 3. Скрипт активации (activate_simple.py)
Теперь поддерживает:
- Временные подписки: `python activate_simple.py USER_ID 30`
- Вечные подписки: `python activate_simple.py USER_ID lifetime`
- По умолчанию: `python activate_simple.py USER_ID` → вечная

## 🚀 Использование

### Активировать вечную подписку:

```bash
# Вариант 1: Явно указать "lifetime"
$env:DATABASE_URL="..."; python activate_simple.py 1115719673 lifetime

# Вариант 2: Без параметра (по умолчанию lifetime)
$env:DATABASE_URL="..."; python activate_simple.py 1115719673

# Вариант 3: Ключевые слова
$env:DATABASE_URL="..."; python activate_simple.py 1115719673 forever
$env:DATABASE_URL="..."; python activate_simple.py 1115719673 permanent
```

### Активировать временную подписку:

```bash
# 7 дней
$env:DATABASE_URL="..."; python activate_simple.py 1115719673 7

# 30 дней
$env:DATABASE_URL="..."; python activate_simple.py 1115719673 30

# 365 дней (год)
$env:DATABASE_URL="..."; python activate_simple.py 1115719673 365
```

## 📊 Обновление БД на Railway

### Вариант 1: Через SQL (рекомендуется)

Подключитесь к БД и выполните:

```sql
-- 1. Изменить структуру таблицы
ALTER TABLE subscriptions ALTER COLUMN expires_at DROP NOT NULL;

-- 2. Обновить конкретного пользователя на вечную подписку
UPDATE subscriptions
SET expires_at = NULL, period = 'lifetime'
WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = 1115719673)
AND status = 'active';

-- 3. Проверить результат
SELECT
    u.telegram_user_id,
    s.period,
    s.expires_at,
    CASE
        WHEN s.expires_at IS NULL THEN 'LIFETIME ♾️'
        ELSE 'Expires: ' || s.expires_at::text
    END as type
FROM users u
LEFT JOIN subscriptions s ON s.user_id = u.id
WHERE u.telegram_user_id = 1115719673;
```

### Вариант 2: Через Alembic миграцию

```bash
# Создать миграцию
alembic revision -m "make_expires_at_nullable"

# Применить
alembic upgrade head
```

## 🎯 Примеры использования

### Сценарий 1: Новый пользователь купил lifetime

```bash
$env:DATABASE_URL="postgresql+asyncpg://..."; python activate_simple.py 123456789 lifetime
```

Результат:
```
[*] Creating LIFETIME subscription...
[OK] SUBSCRIPTION ACTIVATED!
     Created: 2025-10-13 20:30:00
     Expires: NEVER (Lifetime)
[SUCCESS] User 123456789 now has access to the bot!
```

### Сценарий 2: Обновить существующего пользователя на lifetime

```bash
# Старая подписка отменится, создастся новая вечная
$env:DATABASE_URL="postgresql+asyncpg://..."; python activate_simple.py 1115719673
```

Результат:
```
[!] User already has 1 active subscription(s):
    - Expires: 2025-11-12 20:15:32
    Cancelled existing subscriptions.

[*] Creating LIFETIME subscription...
[OK] SUBSCRIPTION ACTIVATED!
     Created: 2025-10-13 20:35:00
     Expires: NEVER (Lifetime)
```

### Сценарий 3: Trial на 7 дней

```bash
$env:DATABASE_URL="postgresql+asyncpg://..."; python activate_simple.py 987654321 7
```

## 🔍 Проверка в БД

```sql
-- Посмотреть всех пользователей с вечными подписками
SELECT
    u.telegram_user_id,
    u.first_name,
    s.status,
    s.period
FROM users u
JOIN subscriptions s ON s.user_id = u.id
WHERE s.expires_at IS NULL AND s.status = 'active';

-- Посмотреть всех пользователей с временными подписками
SELECT
    u.telegram_user_id,
    u.first_name,
    s.period,
    s.expires_at,
    EXTRACT(DAY FROM (s.expires_at - NOW())) as days_left
FROM users u
JOIN subscriptions s ON s.user_id = u.id
WHERE s.expires_at IS NOT NULL AND s.status = 'active';
```

## 📈 Статистика

```sql
-- Количество пользователей с разными типами подписок
SELECT
    CASE
        WHEN expires_at IS NULL THEN 'Lifetime'
        WHEN expires_at > NOW() THEN 'Active (Time-limited)'
        ELSE 'Expired'
    END as subscription_type,
    COUNT(*) as count
FROM subscriptions
WHERE status = 'active'
GROUP BY subscription_type;
```

## ⚙️ Настройки по умолчанию

По умолчанию теперь все новые подписки создаются как **вечные** (lifetime).

Чтобы изменить это поведение, измените в `activate_simple.py`:

```python
days = None  # Default: lifetime
```

на:

```python
days = 30  # Default: 30 days
```

## 🎉 Преимущества

| Параметр | Временная | Вечная |
|----------|-----------|--------|
| Срок действия | Ограничен | ♾️ Навсегда |
| Управление | Нужно продлевать | Не требуется |
| БД | `expires_at = дата` | `expires_at = NULL` |
| Для кого | Trial, тесты | Платные клиенты |

---

**Теперь ваши пользователи могут иметь вечный доступ! 🎉**

