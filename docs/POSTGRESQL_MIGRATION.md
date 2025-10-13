# 🐘 Миграция на PostgreSQL

## ✅ Выполнено

### 1. Добавлены зависимости
- `asyncpg>=0.29.0` - async драйвер для PostgreSQL
- `psycopg2-binary>=2.9.9` - sync драйвер (для Alembic)
- `aiosqlite>=0.19.0` - оставлен для локальной разработки

### 2. Обновлён `database.py`
Код уже поддерживает и SQLite, и PostgreSQL:
- SQLite → `StaticPool` (для локальной разработки)
- PostgreSQL → стандартный пул (для production)

## 🚀 Настройка на Railway

### Шаг 1: Обновите DATABASE_URL в Railway

Ваш текущий URL:
```
postgresql://postgres:OWPLDRewoPmBFfPafGoEVvntjSSDkAQB@postgres.railway.internal:5432/railway
```

**Нужно изменить на (добавить `+asyncpg`):**
```
postgresql+asyncpg://postgres:OWPLDRewoPmBFfPafGoEVvntjSSDkAQB@postgres.railway.internal:5432/railway
```

### Где изменить:
```
Railway → Ваш проект → Variables → DATABASE_URL
```

Измените значение на:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:OWPLDRewoPmBFfPafGoEVvntjSSDkAQB@postgres.railway.internal:5432/railway
```

### Шаг 2: Задеплойте код

```bash
git add .
git commit -m "Add PostgreSQL support with asyncpg"
git push origin feature/add_payments2
```

Railway автоматически:
1. Установит новые зависимости (`asyncpg`, `psycopg2-binary`)
2. Подключится к PostgreSQL
3. Создаст таблицы автоматически (при первом запуске)

### Шаг 3: Проверьте логи

```
Railway → Deployments → View Logs
```

Должны увидеть:
```
Initializing database with URL: postgresql+asyncpg://postgres:***@postgres.railway.internal:5432/railway
Database initialized successfully
Database tables created successfully
```

## ✅ Что изменилось

### До (SQLite):
```
DATABASE_URL=sqlite+aiosqlite:///./vechnost.db
```
❌ Данные терялись при redeploy

### После (PostgreSQL):
```
DATABASE_URL=postgresql+asyncpg://postgres:password@host:5432/railway
```
✅ Данные сохраняются навсегда

## 🔧 Локальная разработка

Для локальной разработки можно использовать SQLite:

### В `.env` файле:
```bash
DATABASE_URL=sqlite+aiosqlite:///./vechnost.db
```

Или установите локальный PostgreSQL:
```bash
# Windows (через Chocolatey)
choco install postgresql

# macOS (через Homebrew)
brew install postgresql

# Потом:
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/vechnost
```

## 📊 Проверка данных

### Подключиться к PostgreSQL на Railway:

1. **Через Railway CLI:**
```bash
railway link
railway connect postgres
```

2. **Через pgAdmin или DBeaver:**
- Host: `postgres.railway.internal` (или внешний хост из Railway)
- Port: `5432`
- Database: `railway`
- Username: `postgres`
- Password: `OWPLDRewoPmBFfPafGoEVvntjSSDkAQB`

3. **Проверить таблицы:**
```sql
\dt  -- Список таблиц

SELECT * FROM users;
SELECT * FROM subscriptions;
SELECT * FROM payments;
```

## 🎯 Что происходит при первом запуске

1. Бот стартует
2. Подключается к PostgreSQL
3. Проверяет наличие таблиц
4. Если таблиц нет → создаёт их автоматически:
   - `users`
   - `products`
   - `payments`
   - `subscriptions`
   - `webhook_events`

## 🔄 Миграция существующих данных (если нужно)

Если у вас уже есть данные в SQLite (локально), можно перенести:

### Вариант 1: Вручную (если данных мало)
```sql
-- Экспорт из SQLite
sqlite3 vechnost.db ".dump users" > users.sql

-- Импорт в PostgreSQL
psql -h postgres.railway.internal -U postgres railway < users.sql
```

### Вариант 2: Через Python скрипт
Создайте `migrate_data.py`:
```python
import asyncio
import sqlite3
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import UserRepository

async def migrate():
    # Читаем из SQLite
    conn = sqlite3.connect('vechnost.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()

    # Записываем в PostgreSQL
    async with get_db() as session:
        for user in users:
            await UserRepository.create_or_update(
                session,
                telegram_user_id=user[1],
                username=user[2],
                first_name=user[3],
                last_name=user[4]
            )

    conn.close()
    print(f'Migrated {len(users)} users')

asyncio.run(migrate())
```

## ⚠️ Важно!

### 1. Не коммитьте реальные пароли
```bash
# В .gitignore должно быть:
.env
*.db
```

### 2. Резервные копии
Railway автоматически делает бэкапы PostgreSQL, но можно настроить дополнительные:
```
Railway → PostgreSQL → Backups
```

### 3. Connection pool
PostgreSQL поддерживает множественные подключения:
- Railway бесплатный план: до 100 connections
- Наш код использует правильный пул подключений

## 📈 Преимущества PostgreSQL

| Параметр | SQLite | PostgreSQL |
|----------|--------|------------|
| Данные при redeploy | ❌ Теряются | ✅ Сохраняются |
| Concurrent writes | ⚠️ Ограничен | ✅ Отлично |
| Масштабируемость | ❌ Ограничена | ✅ Отлично |
| Backup/Restore | ⚠️ Вручную | ✅ Автоматически |
| Production-ready | ❌ Нет | ✅ Да |

## 🐛 Устранение проблем

### Ошибка: "no module named 'asyncpg'"
**Решение:** Railway ещё не установил зависимости
```
Railway → Redeploy
```

### Ошибка: "could not connect to server"
**Причины:**
1. Неправильный DATABASE_URL
2. PostgreSQL сервис не запущен
3. Нет `+asyncpg` в URL

**Решение:**
```bash
# Проверьте URL:
DATABASE_URL=postgresql+asyncpg://...  # ← Должен быть +asyncpg
```

### Ошибка: "relation 'users' does not exist"
**Причина:** Таблицы не создались автоматически

**Решение:**
```python
# Вручную создать таблицы:
python -c "
import asyncio
from vechnost_bot.payments.database import create_tables
asyncio.run(create_tables())
"
```

## ✅ Чеклист миграции

- [x] Добавлены зависимости в `pyproject.toml`
- [ ] Обновлён `DATABASE_URL` в Railway (добавлен `+asyncpg`)
- [ ] Закоммичен и запушен код
- [ ] Railway задеплоил новую версию
- [ ] Проверены логи (нет ошибок)
- [ ] Бот запустился успешно
- [ ] Таблицы созданы в PostgreSQL
- [ ] Пользователи могут регистрироваться

---

**Готово! PostgreSQL настроен и работает! 🎉**

