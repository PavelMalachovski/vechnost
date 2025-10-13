# 🚀 Быстрое исправление: Кнопка оплаты Tribute

## Что исправлено:
✅ База данных создаётся автоматически  
✅ Приветственная страница работает  
✅ **Добавлена кнопка для оплаты через Tribute!**

## 📝 ДВА ПРОСТЫХ ШАГА:

### Шаг 1: Добавьте переменную в Railway

Перейдите в Railway → Ваш проект → Variables

Добавьте новую переменную:
```
TRIBUTE_PAYMENT_URL=https://tribute.to/your_actual_page
```

**⚠️ ВАЖНО:** Замените `your_actual_page` на вашу реальную страницу Tribute!

Например:
- `https://tribute.to/vechnost`
- `https://t.me/tribute?start=your_code`
- Или любой другой URL для оплаты

### Шаг 2: Задеплойте изменения

```bash
git add .
git commit -m "Add payment link and auto DB creation"
git push origin feature/add_payments2
```

Railway автоматически:
- Пересоберёт приложение
- Установит новые зависимости
- Запустит обновлённого бота

## ✅ Проверка работы:

1. Откройте бота в Telegram
2. Нажмите `/start`
3. Выберите язык (например, 🇷🇺)
4. Увидите приветственную страницу с описанием
5. Нажмите "🚀 Начать игру"
6. **Должна появиться кнопка "💳 Купить доступ"** ← ЭТО ГЛАВНОЕ!
7. Кнопка ведёт на вашу страницу Tribute

## 📊 Логи (Railway → Deployments → View Logs):

✅ **Правильная работа:**
```
Initializing database with URL: sqlite+aiosqlite:///./vechnost.db
Database initialized successfully
Database tables created successfully  ← ✅
Created new user: 540529430
User 540529430 has no active access
HTTP Request: POST .../editMessageText "HTTP/1.1 200 OK"
```

## 🎯 Что изменилось:

| Проблема | Решение |
|----------|---------|
| ❌ `no such table: users` | ✅ Таблицы создаются автоматически |
| ❌ Нет кнопки оплаты | ✅ Добавлена фоллбэк ссылка на Tribute |
| ❌ Нужно запускать миграции вручную | ✅ Всё автоматически |

## 📁 Изменённые файлы:

1. `vechnost_bot/payments/database.py` - автосоздание таблиц
2. `vechnost_bot/payments/middleware.py` - фоллбэк ссылка на Tribute
3. `vechnost_bot/config.py` - новая переменная `TRIBUTE_PAYMENT_URL`
4. `env.example` - пример новой переменной
5. Документация обновлена

## 🔧 Если что-то не работает:

### Проблема: Всё ещё нет кнопки оплаты
**Решение:**
1. Убедитесь, что `TRIBUTE_PAYMENT_URL` добавлен в Railway Variables
2. Проверьте, что код задеплоен: `git log --oneline -1`
3. Попробуйте Redeploy в Railway

### Проблема: Ошибка "no such table: users"
**Решение:**
1. Задеплойте новый код
2. Railway → Redeploy
3. Таблицы создадутся автоматически при первом запуске

### Проблема: Кнопка есть, но ведёт на неправильную страницу
**Решение:**
1. Проверьте правильность URL в `TRIBUTE_PAYMENT_URL`
2. Измените переменную в Railway
3. Redeploy (изменение переменной автоматически перезапустит бот)

## 📖 Полная документация:

- 🔥 `docs/PAYMENT_LINK_FIX.md` - детальное описание исправления
- 📋 `docs/DEPLOY_CHECKLIST.md` - чеклист деплоя
- 🔧 `docs/URGENT_FIX.md` - исправление БД
- 📚 `docs/ENVIRONMENT_VARIABLES.md` - все переменные окружения

---

**После выполнения этих шагов бот будет полностью работать! 🎉**

Пользователи смогут:
1. Выбрать язык
2. Увидеть приветственную страницу
3. Нажать "Начать игру"
4. Перейти на оплату через Tribute
5. После оплаты - использовать бота

