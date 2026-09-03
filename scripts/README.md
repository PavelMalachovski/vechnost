# Scripts

Вспомогательные скрипты. Каждый берёт `DATABASE_URL` и остальные настройки
из переменных окружения (или `.env`); ни один не содержит учётных данных,
и в примерах ниже только выдуманные Telegram id.

## Администрирование

- **`activate_simple.py`** – выдать пользователю доступ на N дней или навсегда.
- **`check_user_simple.py`** – показать, что база знает о пользователе.
- **`broadcast.py`** – рассылка всем пользователям; без `--confirm` ничего не
  отправляет (см. корневой README, раздел «Broadcasts»).
- **`generate_certificates.py`** – выпустить подарочные сертификаты и QR-коды.
  Коды печатаются в консоль и больше нигде не сохраняются: не вставляйте их в
  документацию, `tests/test_no_secrets.py` это отловит.
- **`sync_products.py`** – подтянуть продукты из Tribute API.

## База данных

- **`check_local_db.py`** – просмотр локальной SQLite базы.
- **`check_railway_db.py`** – просмотр PostgreSQL на Railway.

## Контент и ассеты

- **`generate_card_assets.py`** – детерминированная генерация карточных
  фонов и мастей (см. CLAUDE.md).
- **`fetch_webapp_fonts.py`** – скачать woff2-шрифты для Mini App.

## Разработка

- **`test_webhook.py`** – отправить подписанный вебхук Tribute на локальный
  сервер.
- **`start_webhook_server.py`**, **`run_webhook_server.py`** – запуск
  веб-сервера локально с перезагрузкой.
- **`typecheck.sh`** – mypy на списке модулей, которые обязаны быть
  типизированы (гейт CI).

## Примеры

```bash
python scripts/check_user_simple.py 123456789
python scripts/activate_simple.py 123456789 lifetime
python scripts/broadcast.py --message-file msg.txt --dry-run
python scripts/test_webhook.py
```

## Заметки

1. Скрипты администрирования меняют продовую базу. Проверьте `DATABASE_URL`
   перед запуском.
2. Против Railway удобнее всего запускать через `railway shell`.
3. Ничего из этой папки не должно содержать реальных id, паролей и кодов:
   `pytest tests/test_no_secrets.py` проверяет это на каждом прогоне.
