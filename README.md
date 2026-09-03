# VECHNOST

A Telegram card game for couples and close conversations. Players pick a
themed deck and answer questions one card at a time — from light and playful
to deep and intimate — either as a classic bot with rendered card images or
inside a polished Telegram Mini App.

> Когда слова заканчиваются — начинается VECHNOST.

## What it is

- **Two ways to play.** A classic bot (inline keyboards + rendered card
  images) and a Telegram **Mini App** at `/app` (swipeable card deck,
  animations, haptics). Both print the same cards: the Mini App loads the
  very PNGs the bot composites onto, served from `/assets`.
- **Four decks.** Acquaintance ♥, For Couples ♠, Sex ♣ (18+), Provocation ♦ —
  310 questions/tasks, with 3 progressive levels on the couple-facing decks.
- **Library.** Six modules listed on the Mini App's home screen and read as
  decks of cards: 150 date ideas in 8 categories, the 36 questions to fall in
  love, 25 practices for couples and 25 for yourself, and a year of
  self-reflection prompts. The nude photography masterclass is the exception,
  read as a document: five numbered steps from light to safety, each item a
  schematic drawing beside the words and the tips underneath.
- **Referrals.** `/invite` hands a user a link. Whoever opens the bot through
  it is sent to a discounted Tribute product when the paywall comes up.
- **Russian.** UI and content are Russian throughout, in both front-ends.
  English and Czech were shipped once and have been retired; they are in git
  history, not in the app.
- **Freemium.** The first 5 cards of every deck are free, and the first 3
  items of every Library list; full access unlocks the rest via a one-time
  Tribute payment. «69 ступеней» has no free prefix and is paid outright.
- **Growth features.** Branded shareable card images, a daily
  self-reflection question, and gift certificates you can buy for another
  couple.
- **Couple mode.** Two phones, one shared deck, taking turns — one payment
  covers both partners.
- **69 Steps (18+).** A board game of temptation: 69 cells, four ladders that
  throw a piece upward and three snakes that pull it back to tenderness,
  three Joker cells that deal a task chosen by how far along and how fast
  that player is moving, and a final cell that blocks the dice. Each partner
  picks a suit and walks their own board; the finale unlocks when both are
  standing on 69. Playable on two phones (the dice locks for whoever is not
  on turn) or on one, passed back and forth. Behind the paywall in full. A
  secret cell's instruction reaches only the player standing on it; their
  partner gets the one line written for them.
- **Compatibility test.** Forty questions across eight areas, taken separately
  by both partners and compared. The result names the areas where they are a
  team, the two worth talking about, and the exact questions they answered
  differently — without showing either partner the other's answers. A push
  tells both partners the moment the result is ready.

## Tech stack

| Area | Choice |
|------|--------|
| Language | Python 3.11+ |
| Bot | [python-telegram-bot](https://docs.python-telegram-bot.org) 21.6 (`[job-queue]`) |
| Web / Mini App API | FastAPI + Uvicorn |
| Data | SQLAlchemy 2 (async) — SQLite locally, PostgreSQL in production; Alembic migrations |
| Sessions / cache | Redis (with in-memory fallback) |
| Card rendering | Pillow (Inter / Lora / Forum, Cyrillic-aware font fallback) |
| Payments | [Tribute](https://tribute.to) webhooks |
| Config | pydantic-settings |
| Hosting | Railway (Nixpacks) |

## Project layout

```
vechnost/
├── vechnost_bot/          # Bot + web server
│   ├── bot.py             # Application wiring, JobQueue (daily card, 69-steps nudge)
│   ├── handlers.py        # /start /help /about /reset /activate /invite
│   ├── callback_handlers.py  # Inline-keyboard game flow
│   ├── keyboards.py, callback_models.py
│   ├── logic.py, models.py, i18n.py
│   ├── renderer.py        # Card image rendering (Pillow)
│   ├── freemium.py        # Free-preview rules (shared bot + Mini App)
│   ├── library.py         # Library content loader
│   ├── daily_card.py      # Daily self-reflection push
│   ├── broadcast.py       # Admin broadcast: /broadcast and scripts/broadcast.py
│   ├── compat.py          # Compatibility test: scoring, result assembly
│   ├── referrals.py       # Invite codes and the discounted payment page
│   ├── compat_notify.py   # "Your result is ready" push to both partners
│   ├── steps69.py         # 69 Steps: board, portals, dice, the Joker
│   ├── steps69_notify.py  # "Your piece is waiting on cell 45" nudge
│   ├── storage.py, redis_storage.py, hybrid_storage.py
│   └── payments/          # Tribute integration + Mini App API
│       ├── web.py         # FastAPI app: /app, /api/questions, /api/card, webhooks
│       ├── library_api.py # /api/library
│       ├── rooms.py       # Couple mode: /api/rooms
│       ├── compat_api.py  # Compatibility test: /api/compat
│       ├── steps69_api.py # 69 Steps: /api/steps69
│       ├── throttle.py    # Rate limiting for the public HTTP surface
│       ├── services.py, repositories.py, models.py, database.py
│       ├── webapp_auth.py # Telegram initData validation
│       ├── gifts.py       # Gift certificates
│       └── middleware.py, signature.py, tribute_client.py
├── webapp/                # Mini App (single-file index.html + fonts)
├── data/                  # questions.yaml, translations_ru.yaml, steps69_ru.yaml
│   └── messages/          # Broadcast texts for scripts/broadcast.py
│   └── library/           # Library content, one YAML per module
├── assets/                # Card backgrounds + fonts (Inter, Lora, Forum)
│                          #   library.png and card_back.png are generated
│                          #   by scripts/generate_card_assets.py
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

The Mini App is then served at `http://localhost:8000/app/`, its deck
content at `/api/questions`, and the Library at `/api/library`. In
production `run_webhook.py` starts both the web server and the bot in one
process (this is the Railway start command).

## Configuration

All settings are read from environment variables (or `.env`). See
`env.example` for the full list; the essentials:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather (**required**) |
| `BOT_USERNAME` | Bot handle without `@`, used in card watermark & share links |
| `WEBAPP_URL` | HTTPS URL of the Mini App (`…/app/`); enables the "Play in app" button |
| `WEBAPP_MAIN_APP` | `true` when the bot has a **Main** Mini App (BotFather → Bot Settings → Configure Mini App). Invites become one-tap links: `t.me/<bot>?startapp=…` |
| `WEBAPP_SHORT_NAME` | Short name of a **named** Mini App (BotFather `/newapp`). Invites become `t.me/<bot>/<name>?startapp=…`. Wins over `WEBAPP_MAIN_APP` if both are set |
| `ENABLE_PAYMENT` | `TRUE`/`FALSE` — gate paid content behind Tribute |
| `TRIBUTE_API_KEY`, `TRIBUTE_PAYMENT_URL` | Tribute payment integration. The API key is also what Tribute signs webhooks with |
| `WEBHOOK_SECRET` | Optional second webhook signing key (a relay or test harness in front of the endpoint). Accepted alongside the API key, never instead of it |
| `ADMIN_IDS` | Comma-separated Telegram user ids allowed to run `/broadcast` in the bot. Unset: the command is not registered at all |
| `ADMIN_TOKEN` | Bearer token for `/admin/*`. Falls back to `TRIBUTE_API_KEY`; set it separately so an outbound credential is not also an inbound password |
| `GIFT_PRODUCT_ID`, `GIFT_PAYMENT_URL` | Gift-certificate product (optional) |
| `REFERRAL_PAYMENT_URL`, `REFERRAL_DISCOUNT_PERCENT` | Discounted Tribute product shown to users who arrived on someone's invite link. Unset: referrals are tracked, everyone pays the same |
| `DAILY_CARD_ENABLED`, `DAILY_CARD_HOUR_UTC` | Daily self-reflection push (default on, 17:00 UTC ≈ 19:00 Prague) |
| `DATABASE_URL` | SQLite locally, PostgreSQL in production |
| `REDIS_URL` | Session/cache store (falls back to in-memory) |

When `ENABLE_PAYMENT=FALSE` (the default for local dev) everything is
unlocked and no Tribute setup is needed.

## Deleting a user's data

`/delete_me` asks once, then removes everything the bot holds about the
person: the user row with its access and payment journal, the daily-push
setting, the bot session, and every room, compatibility test and «69
ступеней» board they sat in — those rows are shared with a partner and go
for both, on the same unanimous-consent rule as deleting one test. A gift
certificate they redeemed stays spent but forgets who spent it; anyone they
invited keeps their discount and loses the link. Access does not come back:
a new purchase or certificate is needed.

## Broadcasts

One message to every registered user, through either of two doors onto the
same delivery loop in `vechnost_bot/broadcast.py`.

**From the bot**, for whoever writes the announcement. Set `ADMIN_IDS` to
the Telegram ids that may use it — with it unset the command does not exist.
Then `/broadcast`, send the message (text, photo, video, voice note: it is
copied, so whatever it is made of survives), check the preview, confirm.
`/cancel` drops a draft. Progress is edited into the confirmation message and
a report follows it, naming the ids that failed so they can be messaged by
hand. Admins get `/broadcast` in their own `/` menu; nobody else sees it.

**From a shell**, when a rehearsal or a dry run is wanted:

```bash
python scripts/broadcast.py --message-file msg.txt --dry-run
python scripts/broadcast.py --message-file msg.txt --limit 5   # a rehearsal
python scripts/broadcast.py --message-file msg.txt --confirm
```

Nothing is sent without `--confirm`. Either way a user who has blocked the
bot is counted as blocked and opted out of the daily push, since that is the
same signal, and Telegram's own `retry_after` is honoured rather than raced.

**Webhooks are signed with `TRIBUTE_API_KEY`.** Tribute sends every event
with an HMAC-SHA256 of the body in the `trbt-signature` header, keyed by the
account's API key; there is no separate webhook secret on their side. With
`ENABLE_PAYMENT=TRUE` and no key configured the endpoint rejects every
delivery rather than granting access on a payload it cannot verify: a
webhook grants lifetime access, so anyone who could reach
`/webhooks/tribute` unsigned could POST their own `telegram_user_id` and
become a paying customer. The signature is checked before anything touches
the database and a rejected delivery is not recorded, so Tribute's retry of
it (they retry for about a day) is judged on its own.

What an event does is a table in `payments/tribute_event.py`:
`new_digital_product`, `new_subscription` and `renewed_subscription` grant
access, a cancellation, refund or chargeback revokes it, and any other
event is acknowledged and changes nothing. Access itself is a row in
`subscriptions`; a `payments` row is a journal entry and never counts on
its own.

## Testing

```bash
pytest                    # full suite, across every core (~10s)
pytest -n0                # serially, for a debugger or readable output
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

Recently shipped: freemium funnel, branded card sharing, gift certificates,
Mini App content-API protection, couple mode (`payments/rooms.py`), the
Library — date ideas, the 36 questions, practices, and a daily
self-reflection question that replaced the old "card of the day" push — the
compatibility test (`compat.py`, `payments/compat_api.py`): 40 questions
across 8 areas, answered separately by both partners, compared, and pushed
to both the moment the result is ready — and a single card identity: one
Cyrillic type family (Inter, Lora, Forum), the same printed card art in the
bot and the Mini App, the Library read as a deck, and Russian as the only
language.

Not started: the "Territory of Temptation" 18+ board game (69 steps, dice,
spoilers), and a nude-photography masterclass (blocked on pose illustrations
that don't exist yet). Each has its own design spec under
`docs/superpowers/specs/` and is expected to reuse the `rooms.py`
two-partner pattern.

## License

MIT.
