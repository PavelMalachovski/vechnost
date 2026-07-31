# VECHNOST

A Telegram card game for couples and close conversations. Players pick a
themed deck and answer questions one card at a time — from light and playful
to deep and intimate — either as a classic bot with rendered card images or
inside a polished Telegram Mini App.

> Когда слова заканчиваются — начинается VECHNOST.

## What it is

- **Two ways to play.** A classic bot (inline keyboards + rendered card
  images) and a Telegram **Mini App** at `/app` (swipeable card deck,
  animations, haptics).
- **Four decks.** Acquaintance, For Couples, Sex (18+), Provocation —
  300 questions/tasks per language, with 3 progressive levels on the
  couple-facing decks.
- **Three languages.** Russian, English, Czech — both UI and content.
- **Freemium.** The first 5 cards of every deck are free; full access
  unlocks the rest via a one-time Tribute payment.
- **Growth features.** Branded shareable card images, a daily "card of the
  day" push, and gift certificates you can buy for another couple.
- **Couple mode** *(in flight — see [Roadmap](#roadmap))*: two phones, one
  shared deck, taking turns.

## Tech stack

| Area | Choice |
|------|--------|
| Language | Python 3.11+ |
| Bot | [python-telegram-bot](https://docs.python-telegram-bot.org) 21.6 (`[job-queue]`) |
| Web / Mini App API | FastAPI + Uvicorn |
| Data | SQLAlchemy 2 (async) — SQLite locally, PostgreSQL in production; Alembic migrations |
| Sessions / cache | Redis (with in-memory fallback) |
| Card rendering | Pillow (Montserrat, Cyrillic-aware font fallback) |
| Payments | [Tribute](https://tribute.to) webhooks |
| Config | pydantic-settings |
| Hosting | Railway (Nixpacks) |

## Project layout

```
vechnost/
├── vechnost_bot/          # Bot + web server
│   ├── bot.py             # Application wiring, JobQueue (daily card)
│   ├── handlers.py        # /start /help /about /reset /activate
│   ├── callback_handlers.py  # Inline-keyboard game flow
│   ├── keyboards.py, callback_models.py
│   ├── logic.py, models.py, i18n.py
│   ├── renderer.py        # Card image rendering (Pillow)
│   ├── freemium.py        # Free-preview rules (shared bot + Mini App)
│   ├── daily_card.py      # Daily "card of the day" push
│   ├── storage.py, redis_storage.py, hybrid_storage.py
│   └── payments/          # Tribute integration + Mini App API
│       ├── web.py         # FastAPI app: /app, /api/questions, /api/card, webhooks
│       ├── services.py, repositories.py, models.py, database.py
│       ├── webapp_auth.py # Telegram initData validation
│       ├── gifts.py       # Gift certificates
│       └── middleware.py, signature.py, tribute_client.py
├── webapp/                # Mini App (single-file index.html + fonts)
├── data/                  # questions*.yaml, translations_*.yaml
├── assets/                # Card backgrounds + fonts
├── alembic/               # Database migrations
├── tests/                 # pytest suite
└── docs/                  # Detailed setup/ops guides
```

## Quick start (local)

```bash
git clone <repository-url>
cd vechnost
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp env.example .env   # then edit .env (at minimum TELEGRAM_BOT_TOKEN)
```

Run the **bot** (long polling):

```bash
python -m vechnost_bot
```

Run the **web server + Mini App** (FastAPI):

```bash
python -m uvicorn vechnost_bot.payments.web:app --reload --port 8000
```

The Mini App is then served at `http://localhost:8000/app/` and its content
API at `/api/questions`. In production `run_webhook.py` starts both the web
server and the bot in one process (this is the Railway start command).

## Configuration

All settings are read from environment variables (or `.env`). See
`env.example` for the full list; the essentials:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather (**required**) |
| `BOT_USERNAME` | Bot handle without `@`, used in card watermark & share links |
| `WEBAPP_URL` | HTTPS URL of the Mini App (`…/app/`); enables the "Play in app" button |
| `ENABLE_PAYMENT` | `TRUE`/`FALSE` — gate paid content behind Tribute |
| `TRIBUTE_API_KEY`, `TRIBUTE_PAYMENT_URL`, `WEBHOOK_SECRET` | Tribute payment integration |
| `GIFT_PRODUCT_ID`, `GIFT_PAYMENT_URL` | Gift-certificate product (optional) |
| `DAILY_CARD_ENABLED`, `DAILY_CARD_HOUR_UTC` | Daily card push (default on, 17:00 UTC ≈ 19:00 Prague) |
| `DATABASE_URL` | SQLite locally, PostgreSQL in production |
| `REDIS_URL` | Session/cache store (falls back to in-memory) |

When `ENABLE_PAYMENT=FALSE` (the default for local dev) everything is
unlocked and no Tribute setup is needed.

## Testing

```bash
pytest                    # full suite
pytest tests/test_freemium.py tests/test_webapp_auth.py   # focused
```

Some suites need a local Redis on `localhost:6379`; those are marked with
the `redis` marker and fail only when Redis is absent.

## Deployment

Deployed on **Railway** via Nixpacks. `railway.toml` sets the start command
to `python -m vechnost_bot.run_webhook`, which runs the FastAPI web server
(Mini App + Tribute webhooks) and the Telegram bot together. Database
migrations live in `alembic/`; new columns are also created idempotently at
startup so a fresh deploy works without a manual migration step. See
[`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md) and
[`docs/PAYMENT_SETUP_GUIDE.md`](docs/PAYMENT_SETUP_GUIDE.md) for details.

## Roadmap

Recently shipped: freemium funnel, branded card sharing, daily card push,
gift certificates, full-Cyrillic brand font, Mini App content-API protection.

In flight (open PRs): **couple mode** (two phones, one shared deck, taking
turns), daily-card content curation, and test-config cleanup.

## License

MIT.
