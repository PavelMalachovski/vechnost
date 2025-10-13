# 🛠️ Админские скрипты для управления подписками

## Доступные скрипты

| Скрипт | Назначение | Использование |
|--------|-----------|---------------|
| `list_users.py` | Список всех пользователей | `python list_users.py` |
| `check_user_payment.py` | Детальная информация о пользователе | `python check_user_payment.py USER_ID` |
| `activate_user.py` | Ручная активация подписки | `python activate_user.py USER_ID [DAYS]` |
| `sync_products.py` | Синхронизация продуктов с Tribute | `python sync_products.py` |

---

## 1. Просмотр всех пользователей

### Команда:
```bash
python list_users.py
```

### Вывод:
```
================================================================================
ALL USERS IN DATABASE
================================================================================

Total users: 3

────────────────────────────────────────────────────────────────────────────────

1. ✅ User ID: 1115719673
   Name: Мария Иванова
   Username: @maria_ivanova
   Registered: 2025-10-12 20:30
   📋 Active subscriptions: 1
      → Expires in 29 days (2025-11-11)

2. ❌ User ID: 540529430
   Name: Андрей Петров
   Registered: 2025-10-12 22:15
   📋 No active subscriptions

3. ✅ User ID: 542528637
   Name: Test User
   Username: @testuser
   Registered: 2025-10-12 22:30
   📋 Active subscriptions: 1
      → Expires in 364 days (2026-10-11)

────────────────────────────────────────────────────────────────────────────────

SUMMARY:
  Total users: 3
  With access: 2
  Without access: 1

================================================================================
```

---

## 2. Проверка конкретного пользователя

### Команда:
```bash
python check_user_payment.py 1115719673
```

### Что показывает:
- ✅ Данные пользователя (имя, username, дата регистрации)
- 📋 Все подписки (активные и неактивные)
- 💳 Все платежи
- 🔔 Последние вебхуки от Tribute
- 🎉 Итоговый статус доступа

### Пример вывода:
```
============================================================
Checking user: 1115719673
============================================================

✅ USER FOUND:
   ID: 1
   Telegram ID: 1115719673
   Username: @maria_ivanova
   Name: Мария Иванова
   Created: 2025-10-12 20:30:00

────────────────────────────────────────────────────────────

📋 SUBSCRIPTIONS (1):

   ✅ Subscription ID: 1
      Tribute ID: sub_abc123
      Status: active
      Starts: 2025-10-12 22:30:00
      Ends: 2025-11-12 22:30:00
      Created: 2025-10-12 22:30:00

────────────────────────────────────────────────────────────

💳 PAYMENTS (1):

   ✅ Payment ID: 1
      Tribute ID: pay_xyz789
      Amount: 999 RUB
      Status: succeeded
      Created: 2025-10-12 22:30:00

────────────────────────────────────────────────────────────

🔔 RECENT WEBHOOK EVENTS (2):

   ✅ Event ID: 1
      Type: subscription.created
      Tribute ID: evt_111
      Processed: True
      Created: 2025-10-12 22:30:00

   ✅ Event ID: 2
      Type: payment.succeeded
      Tribute ID: evt_222
      Processed: True
      Created: 2025-10-12 22:30:15

============================================================
🎉 RESULT: USER HAS ACTIVE ACCESS ✅
============================================================
```

---

## 3. Ручная активация пользователя

### Когда использовать:
- Оплата прошла на стороне Tribute, но вебхук не пришёл
- Нужно дать тестовый доступ
- Пользователь оплатил напрямую (не через Tribute)
- Промо-акция или подарочная подписка

### Команды:

#### Активация на 30 дней (по умолчанию):
```bash
python activate_user.py 1115719673
```

#### Активация на 7 дней (пробный период):
```bash
python activate_user.py 1115719673 7
```

#### Активация на 1 год:
```bash
python activate_user.py 1115719673 365
```

#### Активация навсегда (или на много лет):
```bash
python activate_user.py 1115719673 36500  # 100 лет
```

### Вывод:
```
Activating user 1115719673 for 30 days...
✅ Found user: Мария Иванова

⚠️  User already has 1 active subscription(s):
   - Ends: 2025-11-12 22:30:00

Deactivate existing subscriptions? (y/n): y
   Deactivated existing subscriptions.

✅ SUBSCRIPTION ACTIVATED!
   Subscription ID: 2
   Start: 2025-10-12 22:35:00
   End: 2025-11-11 22:35:00
   Duration: 30 days

🎉 User 1115719673 now has access to the bot!
```

---

## 4. Синхронизация продуктов с Tribute

### Команда:
```bash
python sync_products.py
```

### Что делает:
- Получает список продуктов/подписок из Tribute API
- Сохраняет их в БД
- Обновляет ссылки для оплаты в боте

### Требования:
- `TRIBUTE_API_KEY` должен быть установлен
- Интернет-соединение с Tribute API

### Вывод:
```
Syncing products from Tribute...
✅ Synced 3 products successfully!

Products in database:
  1. Monthly Subscription - 999 RUB
  2. Annual Subscription - 9990 RUB
  3. Lifetime Access - 29990 RUB
```

---

## Запуск на Railway

Все эти скрипты можно запускать на Railway:

### 1. Откройте Railway Shell:
```
Railway → Ваш проект → Shell (иконка терминала)
```

### 2. Запустите нужный скрипт:
```bash
# Список всех пользователей
python list_users.py

# Проверка конкретного пользователя
python check_user_payment.py 1115719673

# Активация пользователя
python activate_user.py 1115719673 30

# Синхронизация продуктов
python sync_products.py
```

---

## Типичные сценарии

### Сценарий 1: Пользователь говорит "я оплатил, но бот не пускает"

```bash
# 1. Проверяем пользователя
python check_user_payment.py 1115719673

# 2. Смотрим результат:
#    - Если "USER HAS ACCESS ✅" → попросить нажать "Проверить статус"
#    - Если "USER DOES NOT HAVE ACCESS ❌" → смотрим подписки и платежи
#    - Если подписок нет → активируем вручную

# 3. Активируем вручную (если нужно)
python activate_user.py 1115719673 30

# 4. Просим пользователя проверить в боте
```

### Сценарий 2: Массовая проверка всех пользователей

```bash
# Смотрим список всех
python list_users.py

# Проверяем подозрительных детально
python check_user_payment.py USER_ID
```

### Сценарий 3: Промо-акция (бесплатный доступ на неделю)

```bash
# Для одного пользователя
python activate_user.py 1115719673 7

# Для нескольких - повторяем команду
python activate_user.py 540529430 7
python activate_user.py 542528637 7
```

### Сценарий 4: Обновление списка продуктов

```bash
# После добавления нового продукта в Tribute
python sync_products.py

# Проверяем, что продукты обновились
python list_users.py  # Или смотрим в БД
```

---

## Дополнительные команды

### Прямой SQL запрос к БД:

```bash
python -c "
import asyncio
from vechnost_bot.payments.database import get_db

async def query():
    async with get_db() as session:
        result = await session.execute('SELECT COUNT(*) FROM users')
        count = result.scalar()
        print(f'Total users: {count}')

asyncio.run(query())
"
```

### Массовая деактивация:

```bash
python -c "
import asyncio
from vechnost_bot.payments.database import get_db
from sqlalchemy import update
from vechnost_bot.payments.models import Subscription
from datetime import datetime

async def deactivate_all():
    async with get_db() as session:
        await session.execute(
            update(Subscription)
            .where(Subscription.status == 'active')
            .values(status='cancelled', end_date=datetime.utcnow())
        )
        await session.commit()
        print('All subscriptions deactivated')

asyncio.run(deactivate_all())
"
```

---

## Безопасность

⚠️ **ВАЖНО:**

1. **Не делитесь БД** - файл `vechnost.db` содержит личные данные пользователей
2. **Не коммитьте БД** - файл уже в `.gitignore`
3. **Резервные копии** - делайте бэкапы БД регулярно:
   ```bash
   # На Railway
   cp vechnost.db vechnost.db.backup.$(date +%Y%m%d)
   ```
4. **Логи активации** - все действия админских скриптов оставляют след в БД

---

## Устранение проблем

### Ошибка "no such table: users"

**Причина**: БД не инициализирована

**Решение**:
```bash
# Запустите бота один раз, чтобы создались таблицы
# Или принудительно создайте:
python -c "
import asyncio
from vechnost_bot.payments.database import create_tables
asyncio.run(create_tables())
"
```

### Ошибка "User not found"

**Причина**: Пользователь не взаимодействовал с ботом

**Решение**: Попросить пользователя нажать `/start` в боте

### Скрипты не работают локально

**Причина**: Переменные окружения не установлены

**Решение**:
```bash
# Создайте .env файл с нужными переменными
cp env.example .env
# Отредактируйте .env
```

---

**Готово! Используйте эти скрипты для управления пользователями и подписками.** 🎉

