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
- **Library.** Six modules. Five are read as decks of cards, one tap behind
  «Практики» on the Mini App's home screen: 150 date ideas in 8 categories,
  the 36 questions to fall in love, 25 practices for couples and 25 for
  yourself, and a year of self-reflection prompts. The nude photography
  masterclass sits on the home screen itself and is read as a document: five
  numbered steps from light to safety, each item a schematic drawing beside
  the words and the tips underneath.
- **Referrals.** `/invite` hands a user a link. Whoever opens the bot through
  it is sent to a discounted Tribute product when the paywall comes up.
- **Russian.** UI and content are Russian throughout, in both front-ends.
  English and Czech were shipped once and have been retired; they are in git
  history, not in the app.
- **Freemium.** The first 5 cards of every deck are free, and the first 3
  items of every Library list; full access unlocks the rest via a one-time
  Tribute payment. «69 ступеней» has no free prefix and is paid outright.
- **Growth features.** A daily self-reflection question, and gift
  certificates you can buy for another couple. Cards stay inside: the Mini
  App has no button that saves a card or sends it out of the app.
- **Couple mode.** Two phones, one shared deck, taking turns — one payment
  covers both partners.
- **69 Steps (18+).** A board game of temptation: 69 cells, four ladders that
  throw a piece upward and three snakes that pull it back to tenderness,
  three Joker cells that deal a task chosen by how far along and how fast
  that player is moving, and a final cell that blocks the dice. Each partner
  picks a suit and walks their own board; the finale unlocks when both are
  standing on 69. Playable on two phones (the dice locks for whoever is not
  on turn) or on one, passed back and forth. Behind the paywall in full. The
  board is drawn after the Lila board, climbing from the bottom, with a
  Cupid's arrow for each ladder and a serpent for each snake; a cell's task
  reaches only the player standing on it, never earlier, and a secret
  cell's partner gets the one line written for them.
- **Compatibility test.** Forty questions across eight areas, taken separately
  by both partners and compared. The result names the areas where they are a
  team, the ones worth talking about, and the exact questions they answered
  differently — without showing either partner the other's answers. A push
  tells both partners the moment the result is ready.

## Tech stack

| Area | Choice |
|------|--------|
| Language | Python 3.11+ |
| Bot | [python-telegram-bot](https://docs.python-telegram-bot.org) 22.8 (`[job-queue]`) |
| Web / Mini App API | FastAPI + Uvicorn |
| Data | SQLAlchemy 2 (async) — SQLite locally, PostgreSQL in production; Alembic migrations |
| Bot sessions | In the bot process's memory (expiring, bounded); Redis when `REDIS_URL` is set |
| Card rendering | Pillow: Inter with a DejaVu fallback per string; the Lora and Forum brand letters are printed into the backgrounds by `scripts/generate_card_assets.py` |
| Payments | [Tribute](https://tribute.to) webhooks |
| Config | pydantic-settings |
| Hosting | Railway, built from the repository's `Dockerfile` |

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
│   ├── storage.py         # Bot sessions: memory, or the Redis REDIS_URL names
│   └── payments/          # Tribute integration + Mini App API
│       ├── web.py         # FastAPI app: /app, /api/questions, webhooks
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
├── scripts/               # Admin and development scripts (scripts/README.md)
├── tests/                 # pytest suite
└── docs/                  # Deployment, CI, payments, environment variables;
                           #   docs/archive/ holds older notes, not maintained
```

## Quick start (local)

```bash
git clone <repository-url>
cd vechnost
python -m pip install --upgrade pip
pip install --require-hashes --no-deps -r requirements-dev.lock   # the versions CI and production run
pip install --no-deps -e .
cp env.example .env   # then edit .env (at minimum TELEGRAM_BOT_TOKEN)
```

`pip install -e ".[dev]"` works too, but resolves today's versions rather
than the locked ones.

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
production `python -m vechnost_bot.run_webhook` runs both, the web server and
the bot, as two supervised child processes (this is the Railway start
command).

Both log the way production does: one JSON line per record, with `level`,
`logger` and `timestamp` (colours when the output is a terminal), and the
room, test and game codes masked out of uvicorn's access log. The app
applies that when it starts, so the plain `uvicorn` command above needs no
flag; production passes the same configuration to uvicorn up front
(`monitoring.uvicorn_log_config()`), which covers uvicorn's first two lines
as well. `LOG_LEVEL=DEBUG` adds the per-tap metrics.

## Configuration

All settings are read from environment variables (or `.env`).
[`docs/ENVIRONMENT_VARIABLES.md`](docs/ENVIRONMENT_VARIABLES.md) lists every
one, generated from the code, and `env.example` is a starting `.env`. The
essentials:

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather (**required**) |
| `ENVIRONMENT` | `production` on the production service: it then refuses to start on a development default (SQLite, an unset `ENABLE_PAYMENT`, no Tribute key with payments on, a Mini App URL that is not `https://`) and lists what to set. Default `development` |
| `BOT_USERNAME` | Bot handle without `@`, used in card watermarks and in invite, referral and gift links |
| `WEBAPP_URL` | HTTPS URL of the Mini App (`…/app/`); enables the "Play in app" button |
| `WEBAPP_MAIN_APP` | `true` when the bot has a **Main** Mini App (BotFather → Bot Settings → Configure Mini App). Invites become one-tap links: `t.me/<bot>?startapp=…` |
| `WEBAPP_SHORT_NAME` | Short name of a **named** Mini App (BotFather `/newapp`). Invites become `t.me/<bot>/<name>?startapp=…`. Wins over `WEBAPP_MAIN_APP` if both are set |
| `ENABLE_PAYMENT` | `TRUE`/`FALSE` — gate paid content behind Tribute |
| `TRIBUTE_API_KEY`, `TRIBUTE_PAYMENT_URL` | Tribute payment integration. The API key is also what Tribute signs webhooks with |
| `WEBHOOK_SECRET` | Optional second webhook signing key (a relay or test harness in front of the endpoint). Accepted alongside the API key, never instead of it |
| `ADMIN_IDS` | Comma-separated Telegram user ids allowed to run `/broadcast` and `/stats` in the bot. Unset: neither command is registered at all |
| `ADMIN_TOKEN` | Bearer token for `/admin/*`. Falls back to `TRIBUTE_API_KEY`; set it separately so an outbound credential is not also an inbound password |
| `ACCESS_PRODUCT_ID` | Tribute product id of the access itself: the Mini App's buy button, its price and the bot's purchase button use exactly this product. Unset: the cheapest synced product that is neither the gift nor the referral discount |
| `GIFT_PRODUCT_ID`, `GIFT_PAYMENT_URL` | Gift-certificate product (optional) |
| `REFERRAL_PAYMENT_URL`, `REFERRAL_DISCOUNT_PERCENT` | Discounted Tribute product shown to users who arrived on someone's invite link. Unset: referrals are tracked, everyone pays the same |
| `DAILY_CARD_ENABLED`, `DAILY_CARD_HOUR_UTC` | Daily self-reflection push (default on, 17:00 UTC ≈ 19:00 Prague) |
| `DATABASE_URL` | SQLite locally, PostgreSQL in production |
| `REDIS_URL` | Where bot sessions live. Unset: the bot's own memory, each forgotten `SESSION_TTL` seconds (default 3600) after its last save. Set: that Redis, and an outage is reported rather than papered over. Nothing starts a Redis for you |

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

## Where people come from, and what they do

`/stats` in the bot (for `ADMIN_IDS` only) reads the funnel off the
`events` table: new and active people, activation on day one, where people
came from, sessions for two and partners who joined, the paywall, the
«Открыть всё» tap and the purchase, gifts and refunds, and who came back on
day 1 and day 7. Every line is people over the last 7 and 30 days.

**Tag every link you publish.** Add `src_<tag>` to the bot link or to the
Mini App link, one tag per channel: `https://t.me/<bot>?start=src_tiktok`,
`https://t.me/<bot>/<app>?startapp=src_blogger_anna`. A tag is up to 32
lowercase letters, digits, `_` or `-`. A person counts for the channel of
their first arrival; referrals, invites and gift certificates count as
`ref`, `invite` and `gift` by themselves, and a link without a tag as «без
метки».

What is kept is a name and one token from a fixed list (a deck, a Library
module, the paywall's door): never an answer, a card, a name or a room
code. `/delete_me` erases a person's events, and the daily sweep drops
everything older than 400 days.

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

## Payments

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
access; a cancellation keeps it until the end of the period already paid
for; a refund or a chargeback revokes it at once; any other event is
acknowledged and changes nothing. Access itself is a row in
`subscriptions`; a `payments` row is a journal entry and never counts on
its own. Setting Tribute up, and what to check when a payment did not turn
into access: [`docs/PAYMENT_SETUP_GUIDE.md`](docs/PAYMENT_SETUP_GUIDE.md).

## Testing

```bash
pytest                    # full suite, across every core (~30s)
pytest -n0                # serially, for a debugger or readable output
pytest --cov              # with coverage, as CI measures it
pytest tests/test_freemium.py tests/test_webapp_auth.py   # focused
```

Some suites need a local Redis on `localhost:6379`; those are marked with
the `redis` marker and are skipped, with a reason, when nothing listens there.
CI also holds coverage to a floor that only rises and the package's type
errors to `.mypy-baseline`; [`docs/CI_CD.md`](docs/CI_CD.md) says how.

## Deployment

Deployed on **Railway**, which builds the repository's `Dockerfile`
(`railway.toml`). The image installs `requirements.lock` - exact versions,
checked against their hashes - so nothing is resolved at deploy time, and CI
builds and smokes the same image before a merge can reach production. Its
command, `python -m vechnost_bot.run_webhook`, runs the FastAPI web server
(Mini App + Tribute webhooks) and the Telegram bot together and stops both
cleanly on SIGTERM. Database migrations live in `alembic/`; new columns are
also created idempotently at startup so a fresh deploy works without a
manual migration step. See
[`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md),
[`docs/CI_CD.md`](docs/CI_CD.md) and
[`docs/PAYMENT_SETUP_GUIDE.md`](docs/PAYMENT_SETUP_GUIDE.md) for details.

## Roadmap

Shipped: the freemium funnel, branded card sharing, gift certificates, couple
mode (`payments/rooms.py`), the Library (date ideas, the 36 questions,
practices and a daily self-reflection question), the compatibility test
(`compat.py`), «69 ступеней» (`steps69.py`), the nude-photography
masterclass (a `guide` module with generated pose drawings), a single card
identity shared by the bot and the Mini App, and funnel analytics (`/stats`).

What is open - the bot's job scheduling, the Mini App's design tokens and
accessibility, and the rest of the technical backlog - is tracked in
[`docs/AUDIT_2026-09.md`](docs/AUDIT_2026-09.md), section 3.

## License

MIT.
