# 🔍 Проверка и активация пользователей

## Проверка пользователя в БД

Пользователь **1115719673** купил подписку. Вот как проверить статус:

### На Railway (продакшн):

1. Откройте **Railway → Ваш проект → Shell**

2. Запустите скрипт проверки:
   ```bash
   python check_user_payment.py 1115719673
   ```

3. Вы увидите полную информацию:
   - ✅ Данные пользователя
   - 📋 Подписки (активные/неактивные)
   - 💳 Платежи
   - 🔔 Вебхуки от Tribute
   - 🎉 Итоговый статус доступа

### Локально (если БД скопирована):

```bash
# Если у вас есть копия БД vechnost.db
python check_user_payment.py 1115719673
```

---

## Ожидаемый вывод

### Если оплата прошла успешно:
```
============================================================
Checking user: 1115719673
============================================================

✅ USER FOUND:
   ID: 1
   Telegram ID: 1115719673
   Username: @username
   Name: Имя Фамилия
   Created: 2025-10-12 20:30:00

────────────────────────────────────────────────────────────

📋 SUBSCRIPTIONS (1):

   ✅ Subscription ID: 1
      Tribute ID: sub_xxxxxxxxxxxxx
      Status: active
      Starts: 2025-10-12 22:30:00
      Ends: 2025-11-12 22:30:00
      Created: 2025-10-12 22:30:00

────────────────────────────────────────────────────────────

💳 PAYMENTS (1):

   ✅ Payment ID: 1
      Tribute ID: pay_xxxxxxxxxxxxx
      Amount: 999 RUB
      Status: succeeded
      Created: 2025-10-12 22:30:00

────────────────────────────────────────────────────────────

🔔 RECENT WEBHOOK EVENTS (2):

   ✅ Event ID: 1
      Type: subscription.created
      Tribute ID: evt_xxxxxxxxxxxxx
      Processed: True
      Created: 2025-10-12 22:30:00

   ✅ Event ID: 2
      Type: payment.succeeded
      Tribute ID: evt_yyyyyyyyyyyyy
      Processed: True
      Created: 2025-10-12 22:30:15

============================================================
🎉 RESULT: USER HAS ACTIVE ACCESS ✅
============================================================
```

### Если оплата не прошла или не обработана:
```
============================================================
Checking user: 1115719673
============================================================

✅ USER FOUND:
   ID: 1
   Telegram ID: 1115719673
   ...

────────────────────────────────────────────────────────────

📋 SUBSCRIPTIONS: None

────────────────────────────────────────────────────────────

💳 PAYMENTS: None

────────────────────────────────────────────────────────────

🔔 WEBHOOK EVENTS: None

============================================================
⚠️  RESULT: USER DOES NOT HAVE ACCESS ❌
============================================================
```

---

## Ручная активация пользователя

Если оплата прошла, но вебхук не пришёл или не обработался, можно активировать вручную:

### Команда:
```bash
python activate_user.py 1115719673
```

Или с указанием срока:
```bash
# 7 дней (trial)
python activate_user.py 1115719673 7

# 30 дней (стандарт)
python activate_user.py 1115719673 30

# 365 дней (год)
python activate_user.py 1115719673 365
```

### Вывод:
```
Activating user 1115719673 for 30 days...
✅ Found user: Имя Фамилия

✅ SUBSCRIPTION ACTIVATED!
   Subscription ID: 2
   Start: 2025-10-12 22:35:00
   End: 2025-11-11 22:35:00
   Duration: 30 days

🎉 User 1115719673 now has access to the bot!
```

---

## Что делать, если пользователь не найден

Если видите `❌ USER NOT FOUND`, это означает, что пользователь **ещё не взаимодействовал с ботом**.

### Решение:
1. Попросите пользователя открыть бота в Telegram
2. Нажать `/start`
3. Выбрать язык
4. Теперь пользователь будет в БД
5. Повторите проверку или активацию

---

## Проверка работы вебхуков Tribute

Если оплата прошла на стороне Tribute, но не активировалась в боте:

### 1. Проверьте настройки вебхука в Tribute:
- URL: `https://your-bot.railway.app/webhooks/tribute`
- Secret: должен совпадать с `WEBHOOK_SECRET` в Railway

### 2. Проверьте логи Railway:
```bash
# В Railway → Deployments → View Logs
# Ищите:
Received webhook event: subscription.created
Processing event: evt_xxxxxxxxxxxxx
```

### 3. Если вебхуки не приходят:
- Проверьте, что FastAPI сервер запущен (отдельный процесс)
- Проверьте, что порт 8000 открыт
- Попробуйте протестировать endpoint:
  ```bash
  curl https://your-bot.railway.app/health
  # Должен вернуть: {"status":"healthy"}
  ```

### 4. Если вебхук пришёл, но не обработался:
- Проверьте логи на ошибки
- Убедитесь, что `WEBHOOK_SECRET` правильный
- Проверьте, что пользователь есть в БД

---

## Быстрая проверка конкретно для 1115719673

### Шаг 1: Проверьте статус
```bash
python check_user_payment.py 1115719673
```

### Шаг 2а: Если доступ есть
✅ Всё в порядке! Пользователь может использовать бота.

### Шаг 2б: Если доступа нет, но оплата прошла на Tribute
Активируйте вручную:
```bash
python activate_user.py 1115719673 30
```

### Шаг 3: Попросите пользователя проверить
Пользователь должен:
1. Открыть бота
2. Нажать "🔄 Проверить статус оплаты"
3. Увидеть сообщение "✅ Доступ подтверждён"
4. Выбрать тему игры

---

## Диагностика проблем

| Симптом | Возможная причина | Решение |
|---------|------------------|---------|
| `USER NOT FOUND` | Пользователь не открывал бота | Попросить нажать `/start` |
| `USER DOES NOT HAVE ACCESS` + нет подписок | Вебхук не пришёл | Проверить вебхуки Tribute, активировать вручную |
| `USER DOES NOT HAVE ACCESS` + есть подписка `status=pending` | Платёж не завершён | Проверить статус в Tribute |
| `USER HAS ACCESS` но бот не пускает | Кэш | Пользователь должен нажать `/reset` или "Проверить статус" |

---

## Массовая проверка пользователей

Для проверки всех пользователей:

```bash
python -c "
import asyncio
from vechnost_bot.payments.database import get_db
from sqlalchemy import select
from vechnost_bot.payments.models import User

async def main():
    async with get_db() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f'Total users: {len(users)}')
        for user in users:
            print(f'{user.telegram_user_id}: {user.username or user.first_name}')

asyncio.run(main())
"
```

---

**Готово! Используйте эти скрипты для проверки и управления подписками пользователей.** 🚀

