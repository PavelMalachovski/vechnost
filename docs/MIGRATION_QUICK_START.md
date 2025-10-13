# ⚡ Быстрый старт миграции на PostgreSQL

## 🎯 Что сделать ПРЯМО СЕЙЧАС:

### Шаг 1: Обновите DATABASE_URL в Railway

Ваш текущий URL:
```
postgresql://postgres:OWPLDRewoPmBFfPafGoEVvntjSSDkAQB@postgres.railway.internal:5432/railway
```

**Измените на (добавьте `+asyncpg`):**
```
postgresql+asyncpg://postgres:OWPLDRewoPmBFfPafGoEVvntjSSDkAQB@postgres.railway.internal:5432/railway
```

### Где:
```
Railway.app → Ваш проект → Variables → DATABASE_URL
```

---

### Шаг 2: Задеплойте код

```bash
git add .
git commit -m "Migrate to PostgreSQL with asyncpg support"
git push origin feature/add_payments2
```

---

### Шаг 3: Дождитесь деплоя

Railway автоматически:
- ✅ Установит `asyncpg` и `psycopg2-binary`
- ✅ Подключится к PostgreSQL
- ✅ Создаст все таблицы

---

### Шаг 4: Проверьте логи

```
Railway → Deployments → View Logs
```

Должно быть:
```
✅ Initializing database with URL: postgresql+asyncpg://...
✅ Database initialized successfully
✅ Database tables created successfully
```

---

## ✅ Всё!

Теперь:
- ✅ Данные **не потеряются** при redeploy
- ✅ Пользователи сохраняются в PostgreSQL
- ✅ Платежи записываются в БД
- ✅ Готово к production

---

## 🔍 Как проверить, что работает:

1. Откройте бота в Telegram
2. Нажмите `/start`
3. Выберите язык
4. Нажмите "Начать игру"

### Проверьте БД:
```bash
# В Railway Shell:
python check_user_payment.py YOUR_TELEGRAM_ID
```

Если видите пользователя → всё работает! ✅

---

**Время выполнения: 2 минуты** ⏱️

