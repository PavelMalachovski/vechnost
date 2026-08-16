# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

VECHNOST is a Telegram card game for couples. Two front-ends share one
content set and one payment/access model:

1. **Bot** (`python-telegram-bot`, long polling) — inline keyboards; each
   card is a rendered PNG (Pillow). `/start` opens straight on the welcome
   screen (logo photo, then the greeting) — there is no language chooser.
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

- **Content** is Russian only: one deck file `data/questions.yaml` and one
  UI file `data/translations_ru.yaml`, loaded by `logic.py` / `i18n.py`.
  Themes and levels are defined by `models.py` (`Theme`, `ContentType`).
  English and Czech are retired — `questions_en/cs.yaml`,
  `translations_en/cs.yaml` and `language_keyboards.py` are deleted and live
  in git history, one revert away. `i18n.Language` has a single member; use
  `Language.coerce(code)` to read a stored or client-supplied `en`/`cs`,
  which comes back as Russian instead of raising.
- **Library content** lives in `data/library/` — one YAML per module
  (`dates`, `fall_in_love`, `practices_self`, `practices_couples`,
  `reflection`). `library.py` loads it and deliberately imports neither
  FastAPI nor python-telegram-bot, so the bot, the API and the tests can all
  use it. The files carry the `_ru` suffix and are the only ones there is.
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
- **The compatibility test** is the second two-partner feature and follows a
  similar shape: `compat.py` is the domain layer (content, scoring, result
  assembly — no FastAPI or python-telegram-bot imports, exactly like
  `library.py`, so the API, the bot and the tests all use it directly),
  `payments/compat_api.py` serves it at `/api/compat`, and `compat_tests`
  stores it. Unlike rooms it has **no TTL** — a completed test is meant to
  be re-read months later — and completing a retake deletes the pair's
  previous sessions outright (`CompatTestRepository.delete_superseded`)
  rather than keeping a history. A completed test is also immutable:
  `/answer` returns 409 once both partners have finished, so neither partner
  can quietly revise a conclusion the other has already read. Either
  participant can erase the whole thing with `DELETE /api/compat/{code}`,
  finished or not — the answers are about their sex life, money and trust,
  and neither of them should have to complete another eighty questions to
  get rid of them.
- **A partner's individual answers never leave the server.** `/api/compat`
  returns counts while a test is in progress, and zones, verdict texts,
  percentages and question numbers once both finish — never the raw 1-5
  answers, and **no per-sphere score**. A score is `(avg_a + avg_b) / 2` over
  five questions, so a partner who knows their own five could solve
  `sum_theirs = 10 * score - sum_mine` exactly; it stays inside
  `build_result` as a list parallel to the results, next to `both_low_flags`.
  Only `percent` is public — one coarse global number, deliberately so.
  `tests/test_compat_api.py` asserts this on the raw response body
  (`"creator_answers" not in body`) rather than on parsed fields, on purpose:
  a leak under an unexpected key would slip past a field-level check, and
  one test tries the reconstruction arithmetic outright.
  `compat_notify.py` sends both partners a push the moment the test
  completes, since the second partner often finishes hours later and would
  otherwise never come back to read it.
- **Card rendering** (`renderer.py`) draws only the question text, and
  auto-picks between **Inter** (the card and UI face) and **DejaVu** (the
  last-resort fallback) per string, so a text in an alphabet Inter lacks
  degrades instead of tofuing. The brand's other two faces are the
  *generator's*, not the renderer's: **Lora** (the `VECHNOST` wordmark) and
  **Forum** (the `V`/`Λ` letters and the `2`/`3` ranks) are printed into the
  backgrounds by `scripts/generate_card_assets.py`, which loads them by
  filename — go there if a wordmark or rank looks wrong. All four ship in
  `assets/fonts/` with Cyrillic; if you touch fonts, keep that coverage —
  Russian is the only audience. Note Forum has no Greek capital lambda
  glyph, so the `Λ` mark is a `V` rotated 180°.
- **Both front-ends print the same cards.** The Mini App does not draw a CSS
  likeness — it loads the very PNGs the bot composites onto, through a
  read-only `/assets` mount in `payments/web.py` (`CARD_ART` / `LIBRARY_ART`
  in `webapp/index.html`). Two of those faces are generated rather than
  drawn by hand: `assets/backgrounds/library.png` (the Library and the daily
  prompt) and `assets/backgrounds/card_back.png` (the shared dark back) come
  from `scripts/generate_card_assets.py`, which crops the suit emblems out
  of the existing deck art and is deterministic — re-running it reproduces
  the committed bytes. Regenerate and commit the PNGs; don't hand-edit them.
  The suits are Acquaintance ♥, For Couples ♠, Sex ♣, Provocation ♦.
- **DB schema.** SQLAlchemy models in `payments/models.py`, Alembic
  revisions in `alembic/`. Deploys run `create_all`, which never alters
  existing tables, so new columns are **also** added idempotently at
  startup (`payments/database.py::_ensure_*`). When you add a column, do
  both: the model + an alembic revision + the idempotent startup add.

## Conventions

- The Mini App is a single self-contained `webapp/index.html` (inline CSS +
  JS, `I18N` object for strings). Its UI strings are separate from the bot's
  YAML translations — update **both** when changing shared copy. `I18N` is
  one flat dictionary now, not a per-language map, and there is no language
  chip row.
- New user-facing text is Russian. There is no second language to fill in.
- **No em dash in card content.** `data/questions.yaml` and
  `data/library/*.yaml` hold zero long dashes; use an en dash `–` or rewrite
  the sentence. `tests/test_no_em_dash.py` guards eight codepoints over
  those files. Interface strings (`data/translations_ru.yaml`,
  `webapp/index.html`) are deliberately outside that rule and still use `—`.
- **One swipe engine, one stage builder.** The game deck and the Library
  deck share `buildStage` and the same drag handler in
  `webapp/index.html`; the Library plugs in through `drag.onAdvance` /
  `drag.onBack` rather than owning a second copy. The gesture splits by axis
  at 8px of travel — vertical scrolls the card text inside its fixed band
  (with a fade at whichever edge is hiding something; long text scrolls, it
  no longer shrinks through size steps), horizontal swipes the card. Extend
  those, don't fork them.
- Prefer adding tests next to the feature (`tests/test_<feature>.py`); the
  suite runs offline (no network, Tribute mocked).
- Brand: dark aubergine background, pink gradient accents, playing-card
  motifs (suits, "V" emblem). Keep card watermarks/share images on-brand.

## Gotchas

- Editing content can silently break things that reference it by position,
  not just by text match. `payments/rooms.py` stores a `card_order` of list
  positions and indexes into `localized_game_data` with it, so inserting or
  removing a question mid-deck changes what every live room (24-hour TTL) is
  showing. `library.question_of_the_day` maps day-of-year to a
  flat index across `data/library/reflection_ru.yaml`'s blocks — keep the
  block sizes at 31/30×10/34 (`tests/test_library.py` enforces them). The
  daily push no longer draws from the decks and there is no curated
  exclude-list file to keep in sync anymore.
- The Library's 18+ gate (`nsfw=1` on `GET /api/library` and
  `GET /api/library/{module_id}`) is client-asserted: the client sends the
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
