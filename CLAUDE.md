# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

VECHNOST is a Telegram card game for couples. Two front-ends share one
content set and one payment/access model:

1. **Bot** (`python-telegram-bot`, long polling) — inline keyboards; each
   card is a rendered PNG (Pillow).
2. **Mini App** (`webapp/index.html`, served by FastAPI at `/app`) — a
   swipeable card deck; content comes from `GET /api/questions`.

The FastAPI app in `vechnost_bot/payments/web.py` also handles Tribute
payment webhooks. In production `run_webhook.py` runs the web server and the
bot in one process.

## Commands

```bash
pip install -e ".[dev]"                 # install with dev deps
python -m vechnost_bot                   # run the bot (polling)
python -m uvicorn vechnost_bot.payments.web:app --reload --port 8000  # web + Mini App
pytest                                   # run tests
pytest tests/test_freemium.py -q         # run one suite
```

- Pytest config lives in `pyproject.toml` under `[tool.pytest.ini_options]`
  (`asyncio_mode = "auto"`). Do **not** re-add a `pytest.ini` — a
  `[tool:pytest]` header there silently disables the pyproject config.
- Redis-dependent tests need `localhost:6379`; they carry the `redis`
  marker. Absent Redis, they fail — that's environmental, not your change.

## Architecture notes

- **Content** lives in `data/questions*.yaml` (one file per language) and
  `data/translations_*.yaml`. `logic.py` / `i18n.py` load and localize it.
  Themes and levels are defined by `models.py` (`Theme`, `ContentType`).
- **Library content** lives in `data/library/` — one YAML per module
  (`dates`, `fall_in_love`, `practices_self`, `practices_couples`,
  `reflection`). `library.py` loads it and deliberately imports neither
  FastAPI nor python-telegram-bot, so the bot, the API and the tests can all
  use it. Content is Russian-only for now; other languages fall back to the
  `_ru` file.
- **Freemium is one shared rule, in two constants.** `freemium.py` holds
  `FREE_CARDS_PER_DECK = 5` for the four game decks (used by
  `callback_handlers.py`, `payments/web.py`, and `payments/rooms.py`) and
  `FREE_LIBRARY_ITEMS_PER_LIST = 3` for Library lists (used by
  `payments/library_api.py`). Change a rule there, not at each call site.
- **Access** is decided by `payments/services.py::user_has_access()`
  (payment OR subscription OR certificate OR `ENABLE_PAYMENT=false`). Reuse
  it; don't reinvent access checks.
- **Mini App auth.** `/api/*` endpoints authenticate the caller with
  Telegram `initData` via `payments/webapp_auth.py::validate_init_data`
  (`Authorization: tma <initData>`). The server never ships paid content to
  an unpaid client — enforce access server-side, not in the client.
- **Two-partner features follow `payments/rooms.py`**: a short room code,
  both players polling for state, a 24-hour TTL, and the room inheriting the
  creator's access so one payment covers both. `payments/library_api.py` was
  deliberately modelled on this pattern — extend it for the next two-partner
  feature rather than inventing a second one.
- **Card rendering** (`renderer.py`) auto-picks a font that covers the
  text's alphabet. The bundled **Montserrat** is the brand font and now
  includes Cyrillic; DejaVu is the fallback. If you touch fonts, keep the
  Cyrillic coverage — Russian is the primary audience.
- **DB schema.** SQLAlchemy models in `payments/models.py`, Alembic
  revisions in `alembic/`. Deploys run `create_all`, which never alters
  existing tables, so new columns are **also** added idempotently at
  startup (`payments/database.py::_ensure_*`). When you add a column, do
  both: the model + an alembic revision + the idempotent startup add.

## Conventions

- The Mini App is a single self-contained `webapp/index.html` (inline CSS +
  JS, `I18N` object for strings). Its UI strings are separate from the bot's
  YAML translations — update **both** when changing shared copy.
- New user-facing text goes in all three languages (ru/en/cs).
- Prefer adding tests next to the feature (`tests/test_<feature>.py`); the
  suite runs offline (no network, Tribute mocked).
- Brand: dark aubergine background, pink gradient accents, playing-card
  motifs (suits, "V" emblem). Keep card watermarks/share images on-brand.

## Gotchas

- Editing content can silently break things that reference it by position,
  not just by text match. `payments/rooms.py` indexes into
  `localized_game_data` by list position, so all three language decks must
  stay the same length. `library.question_of_the_day` maps day-of-year to a
  flat index across `data/library/reflection_ru.yaml`'s blocks — keep the
  block sizes at 31/30×10/34 (`tests/test_library.py` enforces them). The
  daily push no longer draws from the decks and there is no curated
  exclude-list file to keep in sync anymore.
- The Library's 18+ gate (`nsfw=1` on `GET /api/library` and
  `GET /api/library/{module}`) is client-asserted: the client sends the
  flag, the server keeps no record that anyone confirmed their age. It
  prevents accidental display, not deliberate access.
- `ENABLE_PAYMENT=false` unlocks everything and skips initData checks — great
  for local dev, but means auth/paywall paths aren't exercised unless you
  flip it on.
- There is a large legacy `docs/` folder with historical setup notes; the
  root `README.md` is the current source of truth.

## Workflow

- Branch from `master`; open a PR (the maintainer merges). Keep PRs focused.
- Verify Mini App changes in a browser against a local server before
  claiming done; verify rendering changes by generating a card image.
