# 🚀 Быстрый старт: Платежная система Vechnost

## ⚡ За 5 минут

### Шаг 1: Настройте Tribute

1. Зарегистрируйтесь на [tribute.ru](https://tribute.ru/)
2. Получите API ключи в личном кабинете
3. Создайте продукт "Vechnost Premium"

### Шаг 2: Настройте переменные окружения

```bash
# Скопируйте пример
cp env.example .env

# Отредактируйте .env
TRIBUTE_API_KEY=your_key_here
TRIBUTE_API_SECRET=your_secret_here
TRIBUTE_WEBHOOK_SECRET=your_webhook_secret_here
PAYMENT_ENABLED=true

# Настройте премиум канал
PREMIUM_CHANNEL_ID=@your_premium_channel
PREMIUM_CHANNEL_INVITE_LINK=https://t.me/+your_invite
AUTHOR_USERNAME=@your_username
```

### Шаг 3: Создайте премиум канал

```bash
1. Создайте приватный Telegram канал
2. Добавьте бота как администратора
3. Создайте invite link
4. Укажите в PREMIUM_CHANNEL_INVITE_LINK
```

### Шаг 4: Настройте webhook

В Tribute укажите webhook URL:
```
https://your-domain.com/webhook/tribute
```

### Шаг 5: Запустите бота

```bash
# Установите зависимости (если еще не сделали)
pip install -r requirements.txt

# Запустите бота
python -m vechnost_bot
```

---

## 🎯 Что получилось?

### Welcome Screen (как у ХЛБ)

```
VECHNOST — игра для пар 💕

[ВОЙТИ В VECHNOST ←]
[ЧТО ТЕБЯ ЖДЁТ ВНУТРИ?]
[ПОЧЕМУ VECHNOST ПОМОЖЕТ?]
[ОТЗЫВЫ О VECHNOST]
[ГАРАНТИЯ]
[💬 Связаться с автором]
```

### Тарифы

**🆓 Бесплатный**
- Базовые темы
- 10 вопросов/день

**⭐ Премиум - 299₽/мес**
- Все темы (Секс, Провокация)
- Неограниченные вопросы
- Премиум канал
- Приоритетная поддержка

### Автоматизация

- ✅ Автоматическая обработка платежей через webhook
- ✅ Автопродление подписок
- ✅ Автоматическая отправка invite в премиум канал
- ✅ Разграничение доступа к премиум контенту

---

## 🧪 Тестирование без Tribute

Для тестирования без настройки Tribute:

```bash
# В .env
PAYMENT_ENABLED=false
```

Все пользователи получат полный доступ.

---

## 📊 Мониторинг

Просмотр логов платежей:

```bash
# Все события платежей
grep "payment" logs/bot.log

# Успешные платежи
grep "payment_completed" logs/bot.log

# Ошибки
grep "ERROR.*payment" logs/bot.log
```

---

## 🎨 Кастомизация цен

Отредактируйте `vechnost_bot/payment_models.py`:

```python
SUBSCRIPTION_PLANS = {
    SubscriptionTier.PREMIUM: SubscriptionPlan(
        price_monthly=299.0,  # Измените цену
        price_yearly=2990.0,  # Измените цену
        # ...
    ),
}
```

---

## 🔧 Полезные команды

```bash
# Проверить подписку пользователя
redis-cli GET subscription:USER_ID

# Просмотреть все платежи
redis-cli KEYS payment:*

# Очистить тестовые данные
redis-cli FLUSHDB
```

---

## 📞 Поддержка

Полная документация: `PAYMENT_INTEGRATION_GUIDE.md`

---

**Готово! 🎉**

Пользователи могут:
1. Запустить `/start`
2. Выбрать язык
3. Увидеть красивый welcome screen
4. Купить премиум
5. Получить доступ к эксклюзивному контенту

**Сделано с ❤️ для Vechnost**

