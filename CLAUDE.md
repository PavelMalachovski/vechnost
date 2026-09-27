# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

VECHNOST is a Telegram card game for couples. Two front-ends share one
content set and one payment/access model:

1. **Bot** (`python-telegram-bot`, long polling) — inline keyboards; each
   card is a JPEG composited by Pillow onto a PNG background. `/start` opens
   straight on the welcome screen (logo photo, then the greeting) — there is
   no language chooser.
2. **Mini App** (`webapp/index.html`, served by FastAPI at `/app`) — a
   swipeable card deck; content comes from `GET /api/questions`.

The FastAPI app in `vechnost_bot/payments/web.py` also handles Tribute
payment webhooks. In production (Railway builds the repository's
`Dockerfile`) `run_webhook.py` supervises the web server and the bot as two
child processes: it exits when either dies, so the platform's restart policy
restarts the pair together, and it passes SIGTERM on to both, so a redeploy
lets uvicorn drain and the bot stop polling cleanly.

## Commands

```bash
pip install --require-hashes --no-deps -r requirements-dev.lock && pip install --no-deps -e .
                                         # the locked versions CI and production run
pip install -e ".[dev]"                 # ...or today's versions, unpinned
python -m vechnost_bot                   # run the bot (polling)
python -m uvicorn vechnost_bot.payments.web:app --reload --port 8000  # web + Mini App
                                         # (logs as production does once the app starts)
pytest                                   # run tests (parallel, ~30s)
pytest -n0                               # ...serially, for a debugger
pytest --cov                             # ...with coverage, as CI measures it
pytest -m "not slow"                     # ...without the fuzzer and the subprocess tests
pytest tests/test_freemium.py -q         # run one suite
ruff check .                             # lint (CI gates on this)
./scripts/typecheck.sh                   # types, strict, on the domain layer (CI gates on this)
python scripts/mypy_ratchet.py           # types, the rest, against .mypy-baseline (CI gates on this)
pytest tests/e2e -n0                     # the two-user suite, in-process
E2E_BROWSER=1 pytest tests/e2e/browser -n0   # the Mini App on an Android in Chromium and an
                                         # iPhone in WebKit (needs .[e2e]); E2E_PHONES=android
                                         # for one phone, -m screens / -m ui_fuzz for the
                                         # screen tour / the UI fuzzer alone
python scripts/smoke_production.py $URL  # read-only smoke of a deployed server
python scripts/smoke_production.py $URL --deep  # ...and its database and bot heartbeat
```

- **Two users, not one.** `tests/e2e` plays both partners against the real
  app with payments on: signed initData, access bought by a signed Tribute
  webhook, a transcript printed on failure. Scenarios, the bot (real
  `create_application()` over a fake Bot API), a Hypothesis fuzzer whose
  reference model *is* the rules, race tests and two browsers. When you
  change a two-partner rule, change the fuzzer's model in
  `test_duo_fuzz.py` with it. `tests/e2e/README.md` has the details.
- **PostgreSQL is tested.** Production runs it and SQLite hid real faults
  (a NULL typed as text, int32 overflow, NUL bytes, row locks).
  `tests/test_postgres.py` runs when `POSTGRES_TEST_URL` is set;
  `E2E_DATABASE_URL` / `E2E_BASE_URL` run the two-user suite on PostgreSQL
  in-process / against a live server. CI (`e2e.yml`) does all three.
- **Railway deploys only green commits** ("Wait for CI" waits for every
  workflow on the commit) and only once `/health` answers (`railway.toml`).
  So anything added to a workflow that runs on `push` gates production;
  and nothing that waits for a deploy may run on `push`, or it deadlocks
  with "Wait for CI". `docs/CI_CD.md` explains the pipeline.

- **The CI gates are `pytest` (with a coverage floor), `ruff check .`,
  `scripts/typecheck.sh` and `scripts/mypy_ratchet.py`, and all of them
  pass.** Keep them passing. CI runs on pull requests, on `master`, and
  nightly; it used to name `main` and `develop`, neither of which exists
  here, so it had never run at all.
  `e2e.yml` gates on the two-user suite the same way.
- **Coverage has a floor that only rises.** CI's `pytest` measures it
  (`[tool.coverage]` in `pyproject.toml`: branches, greenlets and threads,
  and subprocesses, without which the API modules read 30-38 points low and
  `run_webhook.py` 29 % instead of 93 %) and fails below
  `--cov-fail-under` in `ci.yml`: the measured total, rounded down. When a
  change raises the total, raise the floor with it; a change that would
  lower it adds the test instead. Pull requests also get the coverage of the
  lines they change (diff-cover, advisory) in the job summary.
- **Dependencies are locked.** `requirements.lock` is what the production
  image installs and `requirements-dev.lock` (constrained by it) what CI
  installs: exact versions, hashes, wheels only. SQLAlchemy 2.1 broke a
  fresh install with no commit behind it, because nothing pinned the tree.
  Change a dependency in `pyproject.toml`, then regenerate both locks with
  the two commands in `docs/RAILWAY_DEPLOYMENT.md`; `pip check` in CI fails
  if you forget. The nightly `upstream` job runs the suite on today's PyPI,
  unpinned, to hear about a breaking release before a lock update does.
- **`scripts/typecheck.sh` is mypy on a list, not on the repo.** The strict
  settings in `[tool.mypy]` are real but the repo does not satisfy them yet.
  The script names the modules that *do* — the domain layer plus the
  loaders around it — and `--follow-imports=silent` keeps their
  dependencies' errors out. Add a new domain module to that list.
  Note `python -m mypy`: a standalone mypy runs on its own interpreter and
  reports every third-party import as missing.
- **The rest of the package is held to `.mypy-baseline`.** It lists the
  errors `python -m mypy vechnost_bot` reported when the ratchet was set,
  without line numbers; `scripts/mypy_ratchet.py` (a CI gate) fails on an
  error that is not listed and on a listed one that is fixed. Fix a new
  error rather than list it; after fixing old ones, run
  `python scripts/mypy_ratchet.py --update` and commit the smaller file.
- **`ruff format` has never been applied.** CI checks it, advisory, until a
  one-time reformat lands at a moment with no branches in flight; until then
  do not reformat files you are not otherwise changing.
- Pytest config lives in `pyproject.toml` under `[tool.pytest.ini_options]`
  (`asyncio_mode = "auto"`). Do **not** re-add a `pytest.ini` — a
  `[tool:pytest]` header there silently disables the pyproject config.
- **The suite runs in parallel by default** (`-n auto --dist load` in
  addopts) and takes about half a minute on four cores. `-n0` runs it
  serially, which is what a debugger or readable output needs. Two things
  make parallel safe and must stay that way: the Redis tests take a database
  per xdist worker (`_test_db()` in `tests/test_redis_storage.py`), and every
  test gets its own storage from the autouse fixture rather than sharing the
  singleton. A test that takes seconds by design says so with `slow`;
  nothing is marked by its name any more.
- **Warnings that mean a bug are errors** (`filterwarnings` in
  `pyproject.toml`): a RuntimeWarning (a coroutine nobody awaited), a thread
  or unraisable exception, and a deprecation raised in `vechnost_bot`.
  Dependencies' own deprecations stay quiet; the nightly unpinned run is
  where they turn into breakage first. The autouse fixture that disposes of
  every database engine a test builds is what keeps an aiosqlite connection
  from outliving its event loop - its thread used to die with "Event loop
  is closed" dozens of times a run.
- **No test may touch a real Redis unless it asks to.** The session store
  is chosen from `REDIS_URL` on first use and kept for the life of the
  process, so a machine or CI job exporting `REDIS_URL` would otherwise send
  every test's sessions there. `tests/conftest.py` hands each test a fresh
  in-memory store of its own. Tests that genuinely need a server carry the
  `redis` marker: they run against `localhost:6379`, and are **skipped with
  a reason** when nothing is listening. CI starts a Redis service so they
  really run there.
- Nothing needs `TELEGRAM_BOT_TOKEN` exported to run the tests; conftest
  supplies a fake one before anything imports `config`. It also *overrides*
  `DATABASE_URL` with a throwaway SQLite file: tests that merely called
  `get_db()` used to reach whatever the environment named, production
  included under `railway run`.

## Architecture notes

- **Content** is Russian only: one deck file `data/questions.yaml` and one
  UI file `data/translations_ru.yaml`, loaded by `logic.py` / `i18n.py`.
  Themes and levels are defined by `models.py` (`Theme`, `ContentType`).
  English and Czech are retired — `questions_en/cs.yaml`,
  `translations_en/cs.yaml` and `language_keyboards.py` are deleted and live
  in git history, one revert away. `i18n.Language` has a single member; use
  `Language.coerce(code)` to read a stored or client-supplied `en`/`cs`,
  which comes back as Russian instead of raising.
- **Bot sessions live in memory unless `REDIS_URL` says otherwise.**
  `storage.py` keeps a chat's session (theme, level, the 18+ consent) in
  the bot process, each forgotten `SESSION_TTL` seconds after its last save
  and at most `MAX_SESSIONS` of them; with `REDIS_URL` set it uses that
  Redis instead, with a timeout on every call. Nothing starts a Redis
  server: the code that did ignored `REDIS_URL`, froze the event loop for
  seconds on every start, and hid behind a fallback nothing could reach. A
  Redis failure is not papered over with memory either, which would split
  one chat across two stores; the player gets the short apology. The
  memory store serializes like Redis, so a read is a copy: a handler
  changes the session it is handed and the callback registry saves that
  one (the reset button once reset a second copy, which only memory hid).
- **Library content** lives in `data/library/` — one YAML per module
  (`dates`, `fall_in_love`, `practices_self`, `practices_couples`,
  `nude_guide`, `reflection`). `library.py` loads it and deliberately imports neither
  FastAPI nor python-telegram-bot, so the bot, the API and the tests can all
  use it. The files carry the `_ru` suffix and are the only ones there is.
- **Freemium is one shared rule, in two constants.** `freemium.py` holds
  `FREE_CARDS_PER_DECK = 5` for the four game decks (used by
  `callback_handlers.py`, `payments/web.py`, and `payments/rooms.py`) and
  `FREE_LIBRARY_ITEMS_PER_LIST = 3` for Library lists (used by
  `payments/library_api.py`). Change a rule there, not at each call site.
- **Access** is decided by `payments/services.py::user_has_access()`: an
  active, unexpired `subscriptions` row (a lifetime purchase has no expiry;
  a cancelled subscription counts until the end of the period paid for) OR
  an activated certificate that has not been revoked OR
  `ENABLE_PAYMENT=false`. A `payments` row
  is a journal entry and never counts on its own — it used to, and every
  event Tribute sent, a cancellation included, became lifetime access. Reuse
  the function; don't reinvent access checks. The startup backfill that
  carried the old access over reads only payments from before that change
  (`ACCESS_FROM_PAYMENTS_CUTOVER`): a gift's buyer or a chargeback also
  leaves an undated `payments` row, and must not become a customer.
- **A Tribute event does what the table says.** `payments/tribute_event.py`
  parses a delivery (`name`, `created_at`, `sent_at`, and the purchase in
  `payload`) and `action_for(name)` maps it to grant, cancel, revoke or
  ignore: `new_digital_product`, `new_subscription` and
  `renewed_subscription` grant; a cancellation cancels, which keeps access
  until the `expires_at` already paid for; a refund or chargeback revokes at
  once; anything else is acknowledged with a 200, written to
  `webhook_events` with a note, and changes nothing. Add an event there,
  never by substring-matching the name in the handler. Three more rules:
  - **Events apply in the order they happened.** `subscriptions.last_event_at`
    holds the event's own `created_at`, and an older event than the one
    that last decided a row changes nothing: a purchase redelivered after
    its own refund must not grant again.
  - **One event is processed once, whatever its bytes.** Tribute stamps
    every attempt with its own `sent_at`, so besides the body hash a
    delivery is checked against `TributeEvent.idempotency_key` (the purchase
    id, or name, time, buyer and product), stored unique in
    `webhook_events.event_key`.
  - **A gift's refund revokes its certificate, never the buyer's access.**
    A gift certificate carries the `purchase_id` that paid for it (one
    certificate per purchase); a refund or chargeback of that purchase sets
    `certificates.revoked_at`, and a revoked certificate neither activates
    nor counts as access, redeemed or not. The code is sent after the
    transaction commits.
  The paywall sells exactly `ACCESS_PRODUCT_ID` when it is set (both the
  Mini App's button and price, and the bot's purchase button); without it,
  the cheapest synced product that is neither the gift nor the referral
  discount (`services.access_product`).
- **The paywall is one overlay, and access follows the payment.**
  `showPaywall(ctx)` in `webapp/index.html` serves every door - the end of
  the free cards, a room's last free card, the compatibility test, «69
  ступеней», the Library and the masterclass - with a lead line per door
  and one list of what a payment opens (`payItems`, `payPromise`), the same
  lines the bot's `payment.unlock_message` sends: `tests/test_paywall_copy.py`
  compares the two, so change both. Access is not read only at launch any
  more: after «Открыть всё» the app asks again (`refreshAccess`) when it
  comes back into view, a few times while the webhook may still be on its
  way, and on «Уже оплатили? Обновить доступ»; once paid it carries on
  from where the paywall stopped it, and a deck saved on the free preview
  grows to the whole deck instead of starting over (`growOrder`). The bot
  tells a buyer «всё открыто» itself: `payments/grant_notify.py`, sent by
  the webhook after Tribute has its answer, never for a gift, a renewal, a
  duplicate or a refund, and «навсегда» only for a purchase that is.
- **Mini App auth.** `/api/*` endpoints authenticate the caller with
  Telegram `initData` via `payments/webapp_auth.py::validate_init_data`
  (`Authorization: tma <initData>`). The server never ships paid content to
  an unpaid client — enforce access server-side, not in the client.
- **An invite is a link, never a typed code.** All three two-partner
  features draw six-character codes from one alphabet, so a code entered at
  the wrong door failed confusingly and a mistyped character simply refused
  the partner. `invites.py` mints the link and the server puts it in the
  state payload as `invite_url` — the client never spells one, because only
  the server knows how BotFather is configured and therefore which of three
  shapes works: `t.me/<bot>/<app>?startapp=<kind>_<CODE>` for a named Mini
  App (`WEBAPP_SHORT_NAME`, made with `/newapp`), `t.me/<bot>?startapp=…`
  for a **Main** Mini App (`WEBAPP_MAIN_APP`, made under Bot Settings ->
  Configure Mini App — it has no short name at all, which is why it is its
  own shape rather than a value in the other variable), and
  `t.me/<bot>?start=…` when neither exists, where the bot answers with a
  button into the app. The
  prefixes are `s69`, `cmp`, `duo`. The Mini App reads both `start_param`
  and `?screen=&code=` on boot and joins by itself; there are no code
  fields left anywhere in it.
- **Two-partner features follow `payments/rooms.py`**: a short room code,
  both players polling for state, a 24-hour TTL, and the room inheriting the
  creator's access so one payment covers both. Two rules hold across all
  three: a caller who is not a participant gets the **same 404** an unknown
  code gets, never a 403 — the read endpoints are not throttled like `join`,
  and a distinct status was an oracle for sweeping the code space; and the
  second seat is taken by **one conditional UPDATE** (`seat_guest`, WHERE
  the seat is empty), never a read followed by a write, so two partners
  opening one link at once cannot both be seated. A third: every
  read-modify-write of the shared row (`advance`, `answer`, `roll`,
  `finale`) reads it `FOR UPDATE` - `/advance` did not, and a double tap
  turned the card five times on PostgreSQL. And a code that could never have
  been minted (`invites.valid_code`) gets the same 404 without reaching the
  database. `payments/library_api.py` was
  deliberately modelled on this pattern — extend it for the next two-partner
  feature rather than inventing a second one.
- **A free room opens for both the moment either partner pays.** A room
  whose creator had no access holds the five free cards (`trimmed` in its
  state, beside `full_total`). The first poll, join or tap that finds a
  participant with access - creator or guest, bought before joining or in
  the middle of the game - deals the rest of the deck in under the row lock
  (`rooms._deal_the_rest`): the cards already dealt keep their places, the
  rest follow shuffled, and a room that finished on its last free card
  carries on from the next one. It used to be decided once, by the creator,
  at creation (audit B-20). An 18+ room also keeps its seat empty until the
  person opening the link sends `nsfw=1` (403 until then), so a partner who
  says no is never seated. `/api/card?room=` lets the partner who did not
  pay share a card the room has dealt them, and only such a card.
- **Taking a seat makes a pair.** Whichever door the guest came in by,
  the join calls `payments/partners.py::seat_taken` in its transaction,
  right after the conditional UPDATE and never for a creator reopening their
  own game. Both people get a user row (`UserRepository.ensure`: one INSERT
  that does nothing on a conflict, since /start, the app's boot and a join
  can each be first), each becomes the other's
  `users.partner_telegram_user_id` (the latest pairing wins, `partner_since`
  says when), and a newcomer is credited to the creator (`record_invite`,
  see the referral bullet). After the commit, `payments/partner_notify.py`
  tells the creator in the bot that the partner came, with a `web_app`
  button back into that very game; it never raises, and never logs the
  code. `POST /api/me` gives a person who only ever opens the app a row at
  boot and tells the app whether the bot may write to them
  (`allows_write_to_pm`). When it may not, the app asks with Telegram's
  `requestWriteAccess` - on a game with a partner, at most once in
  `WRITE_ASK_EVERY`, and only once that game's screen is up: `show()`
  closes every overlay, and an ask closed that way counted as asked.
- **The compatibility test** is the second two-partner feature and follows a
  similar shape: `compat.py` is the domain layer (content, scoring, result
  assembly — no FastAPI or python-telegram-bot imports, exactly like
  `library.py`, so the API, the bot and the tests all use it directly),
  `payments/compat_api.py` serves it at `/api/compat`, and `compat_tests`
  stores it. Unlike rooms it has **no TTL** — a completed test is meant to
  be re-read months later — and completing a retake deletes the pair's
  *older* sessions outright (`CompatTestRepository.delete_superseded`)
  rather than keeping a history; a newer test still being answered is left
  alone. A completed test is also immutable:
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
  `build_result` as a list parallel to the results and feeds `percent`,
  which is public — one coarse global number, deliberately so. Everything
  else in the result follows from the zones and the divergent questions
  alone: `strengths` and `attention` list every sphere of their zones in
  authored order (they used to be the top three and bottom two *by score*,
  and an order by score leaks one comparison at a time), and
  `compat._framing` reads only those two (it used to say «both low» where
  the zone did not). That is still not nothing — beside your own answer, a
  divergent question pins your partner's to within one or two values — so
  the product says what a partner sees rather than promising they see
  nothing: `compatIntro` in the Mini App and `feature_privacy_desc` in the
  bot. `test_compat.py` holds the property on fuzzed inputs.
  `tests/test_compat_api.py` asserts this on the raw response body
  (`"creator_answers" not in body`) rather than on parsed fields, on purpose:
  a leak under an unexpected key would slip past a field-level check, and
  one test tries the reconstruction arithmetic outright. The result also
  carries `questions` – the text of every divergent question keyed by its
  global number, texts only, never any answer – because «Обсудите вопросы
  №12» is not actionable when neither partner remembers question 12. The
  result screen renders each number as a tap-to-open `<details>` and reads
  in a fixed order: «Сферы, где вы команда», «Обсудите вопросы», then the
  three zone sections («Сфера силы», «Зона роста», «Критическая зона» with
  its critical-block recommendations); the flat «По всем сферам» list and
  the separate «Требуют разговора» block are gone, and the attention
  framing rides on the sphere's own zone card instead.
  `compat_notify.py` sends both partners a push the moment the test
  completes, since the second partner often finishes hours later and would
  otherwise never come back to read it.
- **Every player walks their own board in «69 ступеней».** Two pieces, two
  positions, two roll counts, two Joker slots; `used_jokers` stays shared so
  one game never deals a task twice. A player who reaches 69 stops rolling
  and the turn skips them; the finale unlocks when both are home. A piece is
  one of the deck's four suits and two players may not wear the same one.
- **«69 ступеней» is the third two-partner feature** and follows the same
  shape again: `steps69.py` is the domain layer (board, portals, dice, the
  Joker – no FastAPI or python-telegram-bot imports, like `library.py` and
  `compat.py`), `payments/steps69_api.py` serves it at `/api/steps69`, and
  `steps69_games` stores it. Three things differ from `rooms.py` and are
  deliberate:
  - **Paid outright.** No free prefix, so `create` refuses an unpaid
    caller (402) rather than trimming a payload. Everything after it -
    `join`, `board`, the state, the dice - only asks whether the caller sits
    in the game: a guest joining a paid creator's game plays free, exactly
    as in a room, and refusing them the board would lock them out of it.
  - **No TTL.** A pair who stop at cell 45 come back to cell 45.
    `steps69_notify.py` nudges them about it once, ~20 hours later, and
    gives up after a week; rolling again clears the flag.
  - **The dice are the server's.** The client asks to roll and is told what
    happened. Both phones have to agree on the number anyway, and a client
    that rolled its own could roll sixty-nine sixes.
  - **A suit is never a locked door.** `join` deals the guest whichever suit
    the creator is not wearing rather than refusing a clash. It used to 409
    on a taken piece and both ends defaulted to «hearts», so the ordinary
    invite — neither partner having touched the picker — turned the second
    phone away at the door. That was what "two phones do not work" meant.
  - **No emoji, no music, no reactions.** The board speaks in suits, drawn
    arrows and colour by block; the three were removed on purpose and the
    column behind the reactions went with them.
  Content lives in `data/steps69_ru.yaml`. Portals are declared *on the
  cells* (`kind: ladder` + `to:`), never in a separate table, so a rewritten
  cell cannot lose its link. Ladders are 4→18, 22→40, 42→60, 65→68; snakes
  are 13→2, 35→20, 55→38; Jokers sit on 9, 29 and 50. Overshooting 69 lands
  on 69 rather than bouncing back, and no portal target is itself a portal
  (`test_steps69.py` holds both).
- **A deal reaches exactly one player.** `steps69.cell_view` takes an
  `audience` – `"mover"` gets the instruction, `"partner"` gets only their
  own line (no text, no secret, no Joker task – on two devices each partner
  reads their own tasks and nobody else's, in the payload as well as on
  screen), and `"shared"` (the one-phone game) gets both because there is
  no second device to withhold anything from. With two pieces the state
  carries two cells: yours as `"mover"`, your partner's as `"partner"`. One
  phone shows the seat that just *moved*, never the one on turn next, or
  nobody ever reads the task they were dealt. The board payload
  (`board_view`) is the printed game: titles, portal arrows **and each
  cell's action text**, so a tap on any map square opens what it does (the
  `s69CellInfo` overlay). What can never be read ahead are the deals –
  secrets, partner lines and Joker tasks are not in the board payload; for
  a secret or Joker square the board `text` is its printed teaser.
- **The Joker reads tempo before stage.** `pick_joker` normally draws from
  the third of the board the pair are standing on, but a pair covering more
  than `RUSH_CELLS_PER_TURN` cells per roll get a tender task wherever they
  are: reaching the last third in six rolls means skipping everything that
  makes an ecstatic task land. Tasks already dealt this game are skipped.
- **The masterclass is a `guide`, not a deck.** `library.py` grows a fourth
  module type: numbered `GuideStep`s of `GuideItem`s, each carrying an `art`
  key. The Mini App renders it as a document (drawing left, words right,
  tips under both) on its own `#guide` screen, and the drawings are
  generated from joint coordinates in `ART_POSES` rather than authored as
  path data, so twenty-nine schematics stay consistent and a pose is nudged
  by moving one number. An unpaid caller gets the first step only.
- **A pose drawing has to say which way the body faces.** The figures are
  silhouettes — a torso of two masses joined at a waist, tapered limbs, a
  nose wedge in profile or a mass of hair for a back view (`face:
  'away-left'` is a back view with the head turned) — and each pose carries
  a `view` and a `face`, printed under the drawing as «вид сбоку · свет
  слева». Three things in `artFigure` are load-bearing: the perpendicular
  across the spine is signed so `L` is the frame's left (the other sign
  hangs every left limb off the right shoulder), a body seen edge-on gets a
  narrow torso because shoulders spread in depth there, and **every limb
  rides on a dark seam** (`art-seam`) — without it an arm crossing the
  torso or a leg crossing a leg melts into one mass, which is what a whole
  fresh-eyes audit of these drawings kept finding. The light is drawn as
  the light: a translucent cone from the lamp (`aim` says what it falls
  on), a glowing window pane, stripes lying on the body; a source at the
  viewer's own position (`light: 'front'`, `cam: 'front'`) is named in the
  caption and never drawn, because a glyph between the feet reads as a
  third leg. A figure lit only from behind sets `dark: true` and renders as
  a dark shape with a yellow rim — the rim is the lesson of those two
  cards, not a decoration.
- **Nothing but the front of a card may take a touch.** `.card .back`
  carries `pointer-events: none`. `backface-visibility: hidden` hides the
  back face from the eye but not from the compositor's touch hit test — both
  faces are clip layers and the back is later in the DOM — so a finger in
  the middle of a card landed on the back, behind which there is no
  scroller, and long questions could not be scrolled at all. `elementFromPoint`
  returns `.q-text` and disagrees, so this is invisible to any check made
  from script: it takes real touch input to see. `tests/test_webapp_static.py`
  holds the rule.
- **A fade must never be a mask on a scroller.** `.q-zone` used to carry a
  `mask-image`, and a mask makes its element invisible to hit testing:
  `elementFromPoint` in the middle of a card returned `.front`, so a finger
  drag found no scrollable ancestor and long card text was readable by
  script and unreadable by hand. The fade is an overlay on `.card .front`
  with `pointer-events: none`, and `markZoneEdges` puts the `cut-*` flags on
  the face for that reason. `tests/test_webapp_static.py` holds it.
- **A certificate code is lifetime access to whoever reads it**, unless
  the gift it was bought as is refunded (see the Tribute bullet). Two
  things mint one: a gift bought through Tribute (`payments/gifts.py`) and
  `scripts/generate_certificates.py` for printed vouchers, and the script
  calls the same `create_gift_certificate`, so there is one alphabet and one
  length (`VECH-XXXX-XXXX`) for `tests/test_no_secrets.py` to know. The
  script writes its QR cards to `certificates/`, which `.gitignore` covers
  along with `certificates*/`, `certificate_*.png` and `certificates*.sql`,
  and refuses any other directory inside the checkout that git does not
  ignore. Five live codes were once committed in a review document; they
  are gone from the tree but not from the public history, so they must be
  treated as spent. The repository logs a certificate's id, never its code.
- **Referral discounts are a second Tribute product, not a coupon.** Tribute
  owns the price, so `referrals.payment_url_for` only chooses which of two
  payment pages a user sees. With `REFERRAL_PAYMENT_URL` unset the codes are
  still minted and invites still recorded, and nobody is promised a discount
  that does not exist. Who counts as invited is `users.referred_at`, the
  invitee's own marker, never `referred_by`: that is a link to another
  person and goes when they are erased, and reading it took the discount
  from everyone an erased user had invited. Only a newcomer can be invited
  (`UserRepository.record_referral`): a row younger than
  `referrals.NEW_USER_WINDOW` - the one the same /start just created - with
  nothing bought or redeemed. For anyone already here a ref link changes
  nothing; it used to hand any old user the referral price. An invite
  into a game counts and prices nothing: a newcomer it seats gets
  `referred_by` - one more in the inviter's /invite - and never
  `referred_at` (`UserRepository.record_invite`). The first credit wins,
  whichever kind of link came later.
- **A broadcast has two doors and one delivery loop.** `broadcast.py` owns
  the loop — the pause between sends, the retry that honours Telegram's own
  `retry_after`, and the rule that a user who blocked the bot is opted out
  of the daily push too, since that is the same signal. A chat that was
  never opened is not that signal: "bot can't initiate conversation" (a
  Tribute buyer, anyone who only ever used the Mini App) marks
  `users.can_message` false, which the daily card and a broadcast skip, and
  anything the person does in the bot's chat marks it true again
  (`check_and_register_user`, and the `write_access_allowed` service message
  Telegram sends when they allow the bot to write from the Mini App). It
  used to opt them out for good, and their /start changed nothing.
  `scripts/broadcast.py`
  is the deliberate door and still sends nothing without `--confirm`;
  `/broadcast` in the bot is the convenient one, and it is registered **only**
  where `ADMIN_IDS` names somebody. That gate is the whole safety story the
  script's separateness used to provide: with the variable unset there is no
  command to type and no button for a stray callback to reach, and with it
  set every entry point re-checks the id rather than trusting the flow that
  led there. The draft is `copy_message`d, never re-typed, so a voice note
  or a video broadcasts as well as text; the confirm callback is registered
  ahead of the game's catch-all and with `block=False`, or a send to
  thousands of people would hold every other update behind it.
- **`/delete_me` forgets a person on request.** `privacy.py` asks with two
  buttons and `UserRepository.erase` does it in one transaction: the user
  row (payments and subscriptions cascade), every room, test and board the
  user sat in (one row shared with a partner, gone for both — the same
  unanimous-consent rule as `DELETE /api/compat/{code}`), the bot session;
  a redeemed certificate stays spent but forgets who, and `referred_by`
  links to the user are cleared while the invitees keep `referred_at`, the
  marker their discount reads, and so is the partner link on the other
  side of the pair; their analytics events go with them. Its
  callback is registered ahead of the game's catch-all on a pattern, like
  the broadcast's. Anything new that stores a person must be added to
  `erase`, or the promise is broken.
  The question (`privacy.ask`) also tells the person to cancel a Tribute
  subscription at Tribute: erasing the row does not stop the billing, and
  the next renewal event creates the user again.
- **The bot never answers a failure with silence, or with the wrong
  words.** `bot.py::on_error` logs, then sends the chat one line
  (`errors.something_went_wrong`), never a traceback; an error with no chat
  (a poll, a job) tells nobody, and a getUpdates `Conflict` is only logged.
  In the callback registry an unparseable button is «Неизвестная команда»
  and anything that fails after parsing (storage, database, Telegram) is
  `errors.callback_failed`: parsing sits in its own `try` because pydantic's
  `ValidationError` is a `ValueError` and used to be filed as an unknown
  button. Text no handler asked for, in a private chat, gets
  `handlers.py::free_text_hint`: a pasted `VECH-XXXX-XXXX` gets the
  `/activate` command ready to copy, anything else a pointer to /start and
  /help. The text itself is never logged; it may be a certificate code.
- **Analytics is one table and one rule: a name and one token, never
  text.** `analytics.py` (a domain module: no FastAPI, no
  python-telegram-bot) holds `EVENTS`, each name with the closed set its
  `detail` may come from - a paywall's door, a deck, a Library module -
  and `event_row` drops anything else rather than store it: no answers, no
  card texts, no names, no room codes. `source` is the channel of an
  arrival (`bot_start`, `app_open`): a `src_<tag>` from the bot or Mini App
  link, or `ref` / `invite` / `gift` / `push`; `/stats` credits a person to
  the source of their first arrival. What only the server can know - a
  seat taken, a test finished, a purchase, a refund - is recorded where it
  happens, with `analytics.record` in the same transaction; the Mini App
  may report only `CLIENT_EVENTS` through `POST /api/events`, signed by
  initData or not kept, one `app_open` a day, under `throttle("events")`.
  `/stats` (`stats.py`) is registered only where `ADMIN_IDS` names
  somebody, like `/broadcast`. `/delete_me` erases a person's events and
  the retention sweep drops them after `analytics.KEEP`. Add an event to
  `EVENTS` with its allow-list, never a free-form field.
- **The daily push has one button into the app.** «Играть» and «Библиотека»
  were the same app opened at two screens, and the choice came before the
  reader had seen either. It is one «Зайти в приложение» now, with the
  opt-out beside it. Older pushes already in people's chats still deep-link
  to `?screen=library`, so that route stays alive.
- **The home screen carries what a couple came for.** Playing, the two
  partner features, «69 ступеней» and the masterclass; the five reading
  modules sit one tap deeper behind «Практики» (`HOME_MODULES` in
  `webapp/index.html` says which stay on top). «Практики» is the `#library`
  screen renamed, which is why `LIB_BACK_TO` and the old deep link still
  work.
- **The bot has one door into the app.** The welcome screen offers a single
  Mini App button; the Library and «69 ступеней» rows were removed, because
  the app's own navigation belongs in the app. The chat menu button and the
  command list are published at startup by `bot.py::_publish_entry_points`,
  which is what a user with a cleared history has left to tap. `/broadcast`
  is published there too but **per chat**, scoped to each admin: the global
  list is every user's «/» menu, and an admin command sitting in it invites
  taps that can only ever be refused.
- **The pitch is one list, in one YAML block.** The welcome screen and
  `/about` both describe what VECHNOST contains, and they used to spell that
  out separately — which is how the board, the masterclass and the
  compatibility test came to be missing from both. The four sections live in
  `translations_ru.yaml`'s top-level `features:` block and are rendered by
  `callback_handlers.py::features_block(language, bold=…)`; `bold` is the
  only difference between the hosts, because the greeting is sent with
  `parse_mode="HTML"` and `/about` is plain text. Add a feature there, not at
  each screen. The greeting itself is short on purpose - two sentences, the
  decks in one line, that block, the button (`tests/test_welcome.py` caps
  it): it once ran to 1 900 characters of manifesto before its only button,
  and the long copy lives behind «Что тебя ждёт внутри?» instead.
- **Every button in the bot does something.** A count is text, not a
  button: the calendar's page is a line of its message (`_calendar_text`)
  and a card's number is printed on the card; the calendar shows only its
  cards, no blank padding. `noop` still answers, for buttons already sitting
  in chats (`tests/test_keyboards.py`).
- **Rate limiting lives in `payments/throttle.py`**, as FastAPI
  dependencies (the client's budget is checked before the global one, and an
  attempt counts only once it passes both - refused requests used to spend
  everyone's ceiling, so one address could lock every couple out): `throttle("join")` on anything that takes a six-character
  code, `throttle("render")` on `/api/card`, `throttle("admin")` on the
  admin routes, `throttle("write")` on in-game writes. Windows are
  in-process (every throttled endpoint lives in the single web process;
  the bot runs beside it as a second process), and the `join` bucket also
  has a **global** ceiling because `X-Forwarded-For` is client-settable and
  a per-client budget alone would not bound a code sweep. The per-client
  budget is the **person** where the Mini App calls (`BY_PERSON`: create,
  join, write, render) and the initData validates, keyed `tg:<id>`; the
  address otherwise (anonymous requests, the webhook, admin). Keyed by
  address, strangers behind one carrier NAT shared one `join` and `write`
  budget, and initData that fails validation still counts against its
  address, so nobody spends a budget by claiming an id. `tests/conftest.py`
  resets it between tests; without that a suite creating more rooms than the
  hourly budget starts 429ing halfway through.
- **A Tribute webhook is signed with the API key, and checked first.**
  Tribute sends HMAC-SHA256 of the raw body, keyed by `TRIBUTE_API_KEY`, in
  the `trbt-signature` header; `WEBHOOK_SECRET` is an optional second key
  for a relay or a test harness, accepted alongside, never instead.
  `signature.py` fails closed whenever `ENABLE_PAYMENT` is on and no key is
  configured, and skips verification with payments off, where there is no
  paywall to bypass - but then `apply_webhook_event` applies nothing: a
  grant recorded before launch would still be a subscription the day
  payments are switched on. `apply_webhook_event` verifies before it opens a
  session and writes a `webhook_events` row only for a delivery it
  processed: a rejected one leaves no trace, so Tribute's retry of the same
  bytes is judged on its own. (It used to be recorded under the body's hash
  first, so the correctly signed retry was told "already processed" and the
  payment was lost. A startup step frees those old rows by renaming the hash
  to `released:<hash>` and keeps them: they are the list of payments to
  redeliver from the Tribute dashboard, so nothing has to be copied out
  before a deploy.) An IntegrityError is a duplicate only if the delivery
  is on record afterwards; otherwise the answer is 503 so Tribute redelivers
  (two purchases by a new buyer race to create the user row). The body is
  read as a stream and cut at 64 KB, chunked or not.
  `/admin/*` authenticates against `settings.admin_secret` (`ADMIN_TOKEN`,
  falling back to `TRIBUTE_API_KEY`) with `compare_digest`, and returns 503
  rather than 401 when neither is configured.
- **One code generator, in `invites.py`.** `new_code()` mints the sixteen
  characters that a room, a compat test and a «69 ступеней» game are all
  addressed by; `valid_code()` says what may travel in a link. Codes used to
  be six characters because a partner typed them; they only ever ride inside
  a link now, and 32^6 was a space a patient sweep could cross for a seat in
  a stranger's game. Six-character codes stay valid — they are in the
  database and in links already sent — so the length check is a range, in
  `webapp/index.html` too.
- **Nothing keeps a room or an abandoned test forever.** `retention.py` runs
  a daily sweep at 03:30 UTC (`bot.py::daily_jobs` schedules it) that drops
  rooms past `ROOM_KEEP` and compat tests and games that were never finished
  past `ABANDONED_KEEP`, and the scheduler's own `job_runs` rows past
  `jobs.KEEP`. It deliberately never touches a *completed* compat test
  or a finished game: those have no TTL on purpose and a couple is meant to
  re-read them months later.
- **A daily job runs once a day, whatever restarts in between.** The daily
  card, the «69 ступеней» nudge and the retention sweep are `DailyJob`s
  (`bot.py::daily_jobs`), started by one JobQueue tick a minute in
  `jobs.py`, not `run_daily` jobs: those lost the rest of the list on a
  restart mid-send, lost the whole day on a restart across the slot
  (APScheduler gives a late run one second) and ran twice during a deploy's
  overlap. A day's run is a `job_runs` row claimed by one statement - an
  INSERT that does nothing on a conflict, or an UPDATE taking over a row
  whose lease ran out - and a job moves its cursor after every recipient
  (`run.check()` before, `run.advance()` after; the daily card pages through
  recipients in Telegram-id order, the nudge flags each game the moment it
  is reached). So a bot that was down at the slot sends late within the
  job's window, one that died is resumed after the last person reached, and
  a second bot finds the run taken; at most the one message in flight at a
  crash goes out twice. A stopping bot hands its run back; five failed
  attempts park it until tomorrow. Each run checks in with Sentry Crons when
  a DSN is set, keeping the check-in id on the row so a takeover closes the
  same check-in. The cursor is a person's id for the daily card and is
  cleared when the run finishes. A new bulk send takes a `Run` the same way
  and sends through `broadcast.deliver`; the race tests are in
  `tests/test_postgres.py`, because a SQLite file takes one writer at a
  time (every transaction begins IMMEDIATE), so two bots at once never
  meet there.
- **Chats are handled side by side, one chat in order.**
  `bot.py::PerChatUpdateProcessor` runs up to `CONCURRENT_UPDATES` updates
  at once, but each chat's in the order they came: every handler reads,
  changes and saves that chat's session, and two taps handled at once could
  each save over the other. `config.create_bot` gives the Bot API
  `BOT_API_CONNECTIONS` connections; the default was one, with a one-second
  wait, so a tap during the daily push failed with `Pool timeout`.
- **`/health` is light, `/health/deep` is thorough.** `/health` is
  Railway's healthcheck and touches nothing: a database blip or a restarting
  bot must not block a deploy or recycle a web process that serves fine.
  `/health/deep` runs `SELECT 1` and reads the `heartbeats` row the bot
  rewrites every minute (`heartbeat.py`, registered in `bot.py`'s job
  setup), and answers 503 when the database does not answer or the beat is
  older than `STALE_AFTER` – the only way the web process can see a bot that
  died, or one whose event loop is stuck. `scripts/smoke_production.py
  --deep` checks it; the default smoke does not, because CI serves the web
  process without a bot. Sentry files events under the deployed commit
  (`RAILWAY_GIT_COMMIT_SHA`, else `RELEASE_VERSION`).
- **One log format, and no codes in it.** `monitoring.configure_logging`
  puts one handler on the root logger whose `ProcessorFormatter` renders
  every record – standard library, structlog, uvicorn – as JSON with
  `level`, `logger` and `timestamp` (colours in a terminal). It replaced
  `basicConfig(format="%(message)s")`, under which most lines had neither
  level nor time. uvicorn's access log passes through `MaskInviteCodes`,
  which turns the code in `/api/rooms|compat|steps69/{code}` and in
  `?code=` / `tgWebAppStartParam=` into `***`: the two-partner screens poll,
  and a code is a seat in a stranger's game. `run_webhook.serve_web` starts
  uvicorn with `monitoring.uvicorn_log_config()`; a plain `uvicorn` command
  is brought into line when the app starts (only uvicorn's first two lines
  come before that). Per-tap metrics – callbacks, counters, timers, renders
  – log at DEBUG; `LOG_LEVEL=DEBUG` brings them back.
- **The web app sets its own security headers.** `payments/web.py`'s
  `security_headers` middleware adds `nosniff`, a CSP `frame-ancestors` that
  names `'self'` and Telegram, and a referrer policy that keeps a room code
  out of the `Referer`. Not `X-Frame-Options: SAMEORIGIN`: Telegram Web
  opens a Mini App in an iframe under web.telegram.org, which SAMEORIGIN
  refused, and the app was blank there (a browser test holds this). CORS and
  trusted hosts are configured only when `CORS_ALLOW_ORIGINS` /
  `ALLOWED_HOSTS` are set, so a default deployment is not locked out of
  itself.
- **The web app compresses and caches what it serves.** `GZipMiddleware`
  sits *inside* `security_headers` (it is added first): that middleware
  passes responses on as a stream, and gzip outside it compressed even a
  30-byte `/health`. The static mounts are `CachedStaticFiles`: the page is
  `no-cache` (always revalidated, so a deploy reaches the next launch), the
  fonts keep for a month and the card art for a day with
  `stale-while-revalidate`. None of the file names carry a hash, which is
  why nothing is `immutable`.
- **A module nothing imports is a trap, not an asset.** `security.py`,
  `rate_limiter.py`, `logo_generator.py`, `optimized_renderer.py`,
  `connection_pool.py`, `async_file_ops.py` and `exceptions.py` were all
  deleted: each was reachable only from its own tests, and
  `optimized_renderer.py` in particular was a second renderer sitting beside
  the wired-up one, waiting for someone to tune the wrong file. `throttle.py`
  is the live rate limiter; `renderer.py` is the live renderer. They are one
  revert away in git history if a use for them ever appears. The same goes
  for a function: CI runs `vulture` and `deptry` as advisory steps
  (`[tool.vulture]` / `[tool.deptry]` in `pyproject.toml` list what a
  framework calls by name, and why a dependency nothing imports stays), and
  a finding there is answered in the PR - delete it, or say what uses it.
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
- **No text on a corner mark.** The deck faces print a V and a suit in the
  top-left corner and a Λ and a suit in the bottom-right; `CORNER_MARKS` in
  `renderer.py` holds their boxes, measured on every face. `layout_text`
  lays a card out in the central band as it always did, and only a text too
  long for the band at `MIN_FONT_SIZE` gets the height beside the marks,
  with the lines that pass one narrowed to clear it (down to
  `LONG_TEXT_MIN_FONT_SIZE`); four long «Провокация» cards used to run over
  both marks. `tests/test_card_layout.py` lays out every card and daily
  prompt on its face, and fails if a redrawn face moves a mark out of its
  box.
- **Both front-ends print the same cards.** The Mini App does not draw a CSS
  likeness — it loads the very PNGs the bot composites onto, through a
  read-only `/assets` mount in `payments/web.py` (`CARD_ART` / `LIBRARY_ART`
  in `webapp/index.html`). Two of those faces are generated rather than
  drawn by hand: `assets/backgrounds/library.png` (the Library and the daily
  prompt) and `assets/backgrounds/card_back.png` (the shared dark back) come
  from `scripts/generate_card_assets.py`, which crops the suit emblems out
  of the existing deck art and is deterministic — re-running it reproduces
  the committed bytes. Regenerate and commit the PNGs; don't hand-edit them.
  The suits are Acquaintance ♥, For Couples ♠, Sex ♣, Provocation ♦, and
  `SUIT_SOURCES` in that script is the one place that says which deck card
  each is cut from.
- **The same script also cuts the four suits out on their own**, to
  `assets/suits/*.png` — square RGBA tiles, all from one box so a single
  size scales the set alike. The home-screen fan lays each over its own deck
  card as an Ace's centre pip, because the mark printed in the card's corner
  is about six pixels at the fan's 72×108 and reads as a smudge. Those tiles
  are pinned by hash in `tests/test_card_assets.py` like the two cards, and
  unlike them they really are portable: they carry no text, so a machine
  whose FreeType sets the VECHNOST wordmark a hair differently still cuts
  byte-identical suits but *will* rewrite `library.png` and `card_back.png`.
  If those two turn up modified after a regeneration you did not intend,
  check the diff is confined to the wordmark band and `git checkout` them.
- **DB schema.** SQLAlchemy models in `payments/models.py`, Alembic
  revisions in `alembic/`. Deploys run `create_all`, which never alters
  existing tables, so new columns are **also** added idempotently at
  startup (`payments/database.py::_ensure_*`). When you add a column, do
  both: the model + an alembic revision + the idempotent startup add.
  The startup steps (`_STARTUP_STEPS`) each run in their own transaction
  and a failing one no longer stops the rest; write SQL that PostgreSQL
  accepts (type your NULLs), because a step that only works on SQLite fails
  on every production start. `tests/test_postgres.py` checks that alembic
  and `create_all` build the same schema, indexes included.
- **Indexes follow the model at startup too.** `create_all` indexes a table
  only the day it creates it, so `_ensure_indexes` creates every index the
  model declares that a deployed table lacks, and drops the plain indexes
  that only doubled a unique constraint (`REDUNDANT_INDEXES`, and only
  where the constraint is really there). An index goes in the model and an
  alembic revision; the startup step picks it up by itself. A lookup by
  person ("creator or guest") needs both sides indexed or PostgreSQL scans
  the table; a filter on unfinished rows gets a partial index spelled as
  the query spells it (`finished IS false`). Rooms are deliberately not
  indexed beyond their code: they live a day. `tests/test_postgres.py`
  EXPLAINs the statements the repositories actually send.

## Conventions

- The Mini App is a single self-contained `webapp/index.html` (inline CSS +
  JS, `I18N` object for strings). Its UI strings are separate from the bot's
  YAML translations — update **both** when changing shared copy. `I18N` is
  one flat dictionary now, not a per-language map, and there is no language
  chip row.
- **Design tokens live in the page's `:root`.** Palette, roles, type
  scale, space, radii, shadows, motion, layers and the safe area, in that
  order (`docs/AUDIT_2026-09.md`, section 4). A new rule reads a token; the
  names older rules were written against (`--ink`, `--card-bg`,
  `--muted-on-dark`, ...) are aliases of it, so a colour is spelled once.
  Literals move over to tokens a step at a time, and a step that is meant to
  change nothing is proved by comparing screenshots pixel for pixel.
  `tests/test_webapp_static.py` fails on a `var()` of a name nobody declares,
  which CSS itself would swallow silently.
- New user-facing text is Russian. There is no second language to fill in.
- **No gendered verb forms in user-facing text.** Not «уверен», and not the
  «уверен(а)» bracket either: the reader may be of any gender, and the
  brackets read as a form to fill in. Russian gives you present and future
  tense (no gender), «мне удалось», «случалось ли тебе», nominalisation
  («в чём проявилась моя щедрость»), and agreement with a noun («партнёр
  изменил», «был ли у тебя опыт») — use those. The same goes for the
  reader's partner: «партнёр», never «партнёрша», and no «он/она» – rewrite
  the sentence so it needs no pronoun. `data/questions.yaml`,
  `data/library/*.yaml` and the interface copy carry none.
- **No em dash in user-facing text.** `data/questions.yaml`,
  `data/steps69_ru.yaml` and `data/library/*.yaml` hold zero long dashes;
  use an en dash `–` or rewrite the sentence. `tests/test_no_em_dash.py`
  guards eight codepoints over those files **and over the interface copy**:
  `data/translations_ru.yaml` outright, and `webapp/index.html` across the
  two surfaces a user reads (its `<title>` and the `I18N` literal). Only the
  Mini App's English code comments may carry `—`, where it is correct English
  punctuation. Add a new content YAML to that test's `CONTENT` list, or it
  is simply never checked.
- **The board is not a deck.** «69 ступеней» has its own screens and its own
  state (`G`) in `webapp/index.html`, and the Library modules are listed on
  the home screen rather than behind a «Библиотека» button (the `#library`
  screen stays: the daily push still deep-links to it, so `LIB_BACK_TO`
  records which way a module was entered), and reuses `coopFetch` for auth rather
  than the swipe engine for movement: there is nothing to swipe. The map is a
  serpentine running *downward* (cells 1-6 left to right, 7-12 right to
  left), capped at `30vh` and scrolling inside itself, because twelve rows of
  six otherwise push the dice — the only button that has to be pressable —
  off the bottom of the screen. The music presets are synthesised WebAudio
  beds, not files; swap them for licensed stems when there are any and keep
  the control surface.
- **Readable on every phone, and one Back.** Nothing on the page is set
  under 11px and the page may be zoomed; tile text reads at 4.5:1 on every
  stop of its tile's gradient (the light tiles carry the cards' ink); a
  pressable thing is at least `--tap-min` (44px). Inside Telegram the page's
  own header «←» (`.icon-btn.back`, one per screen) is hidden, because the
  header has Telegram's Back - and Telegram's Back presses the active
  screen's «←», so a screen has exactly one back behaviour. Outside
  Telegram the page's own shows. `tests/test_webapp_readability.py` holds
  all of this on the source; `tests/e2e/browser/test_readability.py` as
  drawn. In a browser test, go back with Telegram's Back
  (`BackButton._cb()`), never a click on a `#…Back`: it is hidden.
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
- **A script in `scripts/` answers `--help` and works through the app.**
  `tests/test_scripts.py` runs every `scripts/*.py --help` in a fresh
  interpreter and fails on a non-zero exit, on output that is not argparse's,
  and on a file written: parse the arguments before touching anything. Read
  and write through the repositories and `settings`, never raw SQL or a
  second `.env` loader - `activate_simple.py`, which wrote subscriptions by
  hand, could not see a lifetime purchase. To grant access by hand, mint one
  certificate (`generate_certificates.py 1`) and send the code.
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
- «69 ступеней» is 18+ and paid, and its age gate is the same client-asserted
  one the Library uses: it prevents accidental display, not deliberate
  access. The app asks before the board's first screen however it is
  entered - the home button, an invite, the nudge - and seats nobody before
  the answer (`nsfwGate`). The paywall behind it is not client-asserted and
  is enforced in `steps69_api.py`.
- The Library's 18+ gate (`nsfw=1` on `GET /api/library` and
  `GET /api/library/{module_id}`) is client-asserted: the client sends the
  flag, the server keeps no record that anyone confirmed their age. It
  prevents accidental display, not deliberate access.
- `ENABLE_PAYMENT=false` unlocks everything and skips initData checks — great
  for local dev, but means auth/paywall paths aren't exercised unless you
  flip it on.
- **`ENVIRONMENT=production` refuses development defaults.**
  `config.production_problems` lists what a production start needs – a
  `postgresql+asyncpg` `DATABASE_URL`, an explicit `ENABLE_PAYMENT`,
  `TRIBUTE_API_KEY` when payments are on, an `https://` `WEBAPP_URL` – and
  `Settings` raises `ProductionConfigError` naming every one. Not a
  `ValueError`: pydantic would repeat every setting, the token and the
  database password included, into the crash log. Development and the test
  suite are unaffected; the production service has to set the variable.
- **`docs/` holds only what is kept true**: `AUDIT_2026-09.md`, `CI_CD.md`,
  `RAILWAY_DEPLOYMENT.md`, `PAYMENT_SETUP_GUIDE.md` and
  `ENVIRONMENT_VARIABLES.md`, whose table of settings is generated from
  `Settings` - after adding, renaming or re-describing a setting, run
  `python scripts/env_docs.py --write` (`tests/test_env_docs.py` fails
  until you do; it also wants every variable read outside `Settings`
  listed). Older notes, plans and reviews are in `docs/archive/` under a
  one-line banner and are not maintained; the root `README.md` is the
  current source of truth.

## Workflow

- Branch from `master`; open a PR (the maintainer merges). Keep PRs focused.
- Verify Mini App changes in a browser against a local server before
  claiming done; verify rendering changes by generating a card image.
