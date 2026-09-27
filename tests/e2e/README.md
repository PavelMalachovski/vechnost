# Two-user E2E

Everything VECHNOST sells a couple needs two people on two phones: a room,
the compatibility test and «69 ступеней» each have a creator and a guest who
poll one row and write to it in turns. This directory plays both of them
against the real app, with payments switched on and nothing mocked but
Telegram itself.

| Layer | File | What it proves | Runs |
|---|---|---|---|
| Scenarios | `test_duo_rooms.py`, `test_duo_compat.py`, `test_duo_steps69.py` | Whole evenings, start to finish: both screens agree, only the right person may move, strangers get the same 404 as a code nobody minted, deals and answers stay on the phone they belong to | every `pytest` |
| Bot | `test_duo_bot.py` | What travels between two users through the chat: an invite turned into a button, a referral, a gift bought by one and redeemed by the other, `/delete_me` taking shared rows for both | every `pytest` |
| Fuzzer | `test_duo_fuzz.py` | Three people (Alice paid, Bob unpaid, Carol a stranger with the link) doing *anything* in any order, checked after every step against a reference model of the rules | every `pytest` (small budget); CI raises it |
| Races | `test_duo_races.py` | The same seat, turn or answer hit by both phones at the same instant | CI, against PostgreSQL |
| Browsers | `browser/test_two_phones.py`, `test_paywall.py`, `test_navigation.py`, `test_design_regressions.py` | Two phones driving the Mini App UI, each scenario on both phone models: the invite link one screen shows opens the other, the waiting phone catches up by itself, no deal leaks to the wrong screen, the paywall and the 18+ doors, Back | CI (`E2E_BROWSER=1`), one job per phone |
| Touch | `browser/test_touch.py` | A long card under real input: a finger in the middle of the text scrolls it, a vertical drag leaves the card alone, a swipe turns it; and the suite breaks the two hit-testing rules on purpose to prove it notices | CI, one job per phone |
| Screens | `browser/test_screens.py` | Every screen and overlay of the Mini App, reached for real, photographed at 320×568, 375×667, 393×852 and 430×932 on each phone | CI on pull requests and at night |
| UI fuzzer | `browser/test_ui_fuzz.py` | Both partners in one room, test or board, tapping, swiping, scrolling and pressing Back at random; checked after every step (errors, unexpected `/api` answers, sideways overflow, Back, the two phones agreeing) | CI on pull requests (short) and at night (long) |

## Running it

```bash
pytest tests/e2e -n0                        # scenarios, bot, a short fuzz (~15 s)
E2E_FUZZ_EXAMPLES=400 E2E_FUZZ_STEPS=100 \
  pytest tests/e2e/test_duo_fuzz.py -n0 -s  # the nightly fuzz (~13 min), prints what it reached

pip install -e ".[dev,e2e]" && python -m playwright install chromium webkit
E2E_BROWSER=1 pytest tests/e2e/browser -n0  # both phones, everything (~6 min per phone)
E2E_BROWSER=1 E2E_PHONES=android pytest tests/e2e/browser -n0 -m "not screens and not ui_fuzz"
                                            # one phone, the deterministic part (what a push runs)
E2E_BROWSER=1 pytest tests/e2e/browser -n0 -m screens   # every screen at four sizes
E2E_UI_FUZZ_RUNS=3 E2E_UI_FUZZ_STEPS=100 E2E_BROWSER=1 \
  pytest tests/e2e/browser -n0 -m ui_fuzz -s             # the nightly UI fuzz (~20 min per phone)
```

Screenshots of every browser step, a Playwright trace of each phone when a
test fails, and `fuzz_coverage.json` go to `E2E_REPORT_DIR` (default
`./e2e-report`, git-ignored).

## Two phones, two engines

Telegram shows a Mini App in Chromium on Android and in WebKit on iOS, so
every browser test runs once per phone model (`browser/phones.py`):

| Phone | Engine | Screen | Telegram says |
|---|---|---|---|
| `android`, Pixel-class | Chromium | 412×915 at 2.625x, touch | `platform: "android"` |
| `iphone`, iPhone 15 Pro-class | WebKit | 393×852 at 3x, touch | `platform: "ios"` |

Both partners of a scenario hold the same model, so a CI job per phone runs
every scenario on one engine, against a live server on PostgreSQL. Locally
the browsers' server runs on a SQLite file unless `E2E_DATABASE_URL` names
another database, and SQLite's single shared connection (audit B-13, H-03)
now and then refuses a partner's first join with «test is full» while the
seat stays empty: a two-phone test that fails that way locally is B-13, not
the test. PostgreSQL does not do it. `E2E_PHONES=android` (or `iphone`) picks the
phones; unset, both run, and a phone whose engine is not installed skips
with the reason. Named in `E2E_PHONES`, a missing engine fails instead: the
iPhone job must not go green by testing nothing.

### What is real touch, and what is not

* **Android (Chromium): all of it.** Taps, swipes and scrolls are CDP
  `Input.dispatchTouchEvent`, which Chromium's compositor hit-tests and
  scrolls exactly as it does a finger - which is what the two hit-testing
  rules in `CLAUDE.md` are about, and what `elementFromPoint` gets wrong.
* **iPhone (WebKit): real input, but not all of it touch.** A tap is
  Playwright's `touchscreen.tap`, WebKit's own touch path. Playwright has no
  touch drag for WebKit and refuses the mouse wheel on a mobile page, so a
  swipe is a real mouse drag (the swipe engine listens to both) and a
  scroll a real press where the finger rests followed by the arrow keys,
  each hit-tested by WebKit itself. Not covered, and not coverable with
  Playwright: a touch drag in WebKit, and everything iOS adds on top of it -
  UIKit's scroll views and gesture recognisers, momentum. Playwright's
  WebKit is the Linux build, not an iPhone.

`test_touch.py` ends by breaking each rule on purpose (a touchable back
face, a mask on the scroller) and recording which probe notices, in
`touch-canary-<phone>.json` and the job summary. On Chromium the back face
stops the real scroll, as it did in production. The mask no longer does:
current Chromium keeps a masked element in its hit test, so that rule is
held by the computed-style probe on every phone.

### Screens

`test_screens.py` walks each phone through every screen and overlay - the
decks, the 18+ question and the paywall, a room, the compatibility test and
«69 ступеней» from their doors to their ends (a partner joins and plays
through the API; the phone hears it through its own poll), the Library, a
practice and the masterclass - and photographs each at 320×568, 375×667,
393×852 and 430×932. `e2e-report/browser/screens/index.html` is the contact
sheet; CI uploads it with the job's artifact and puts the table in the job
summary.

### The UI fuzzer

`test_ui_fuzz.py` seats Alice (paid) and Bob (not) in one room, test or
board through the UI and lets both phones act at random: tap any visible,
enabled control, swipe a card, scroll whatever scrolls, press Telegram's
Back, wait, close and reopen the app, open the invite again. After every
step, on both phones: no page error and no console error; no `/api` answer
the app does not expect (`EXPECTED` lists the 4xx it is built to handle,
each with its reason) and no 5xx; nothing reaching past the sides of the
screen; Back closed the top layer (the overlay, else the screen); the loader
never up for more than 10 s; a way out of every overlay; and once their
polls settle, both phones showing what the server holds for each of them.
At the end both find their way home.

Every arena runs `E2E_UI_FUZZ_RUNS` times for `E2E_UI_FUZZ_STEPS` steps: 1×25
on a pull request, 3×100 at night. A failure prints the seed, the command
that replays it (`E2E_UI_FUZZ_SEED=<seed> ...`) and every step both phones
took; `ui_fuzz_<phone>_<arena>_<seed>.json` keeps what each run did.

### Against a live server, or PostgreSQL

By default the app runs in-process on a throwaway SQLite file. Two switches
change that:

* `E2E_DATABASE_URL=postgresql+asyncpg://…` points the in-process app at
  another database. Production runs PostgreSQL and SQLite hides real
  differences (row locks, typed NULLs, integer ranges), so CI runs the suite
  on both.
* `E2E_BASE_URL=http://127.0.0.1:8000` sends every request over real HTTP to
  a server you started. Scenarios that need in-process powers (the fake
  Telegram, the bot) mark themselves `inprocess_only` and skip; the race
  tests mark themselves `live_only` and run only here, because concurrency
  through one in-process client is not concurrency.

A live server must be started with the harness's keys, the way
`.github/workflows/e2e.yml` does it:

```bash
ENABLE_PAYMENT=true TRIBUTE_API_KEY=e2e-tribute-signing-key \
TELEGRAM_BOT_TOKEN=1234567890:TEST_TOKEN_FOR_UNIT_TESTS \
BOT_USERNAME=vechnost_e2e_bot TRUSTED_PROXY_HOPS=1 \
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/vechnost_e2e \
python -m uvicorn vechnost_bot.payments.web:app --port 8000
```

## How the players are real

A `Player` (`harness.py`) is a Telegram identity as far as the server can
tell: its requests carry initData signed with the bot token exactly the way
Telegram signs it, so `validate_init_data` runs for real. Access is bought
the way a customer buys it, with a `new_digital_product` webhook signed by
the Tribute key. Each player sends their own `X-Forwarded-For`; give two
players the same `ip=` to put a couple on one home Wi-Fi, or strangers
behind one carrier NAT. The throttle budgets a player with valid initData
by their Telegram id, so a shared address shares no budget; the address
keys only what carries no valid initData.

Isolation is by identity, not by database: every player is a fresh random
Telegram id and every game a fresh code, so scenarios can share one live
server and one database without seeing each other.

## Reading a failure

* **Scenarios** print a *two-user transcript* under the failure: every
  request each player made and what came back, in order.
* **The fuzzer** shrinks the run to the shortest sequence of steps that still
  fails and prints it as Python — that sequence is the bug report. The dice
  are the fuzzer's too (it patches `steps69.roll_dice` to the value it drew),
  so a failing game replays exactly.
* **Browsers** leave `e2e-report/browser/<test>/`: numbered screenshots of
  both phones, and `trace-<name>.zip` for `playwright show-trace`.
* **The UI fuzzer** prints its seed, the replay command and the steps; the
  screenshots of both phones at the failure are in its test's folder.
* To show a browser test catches a fault, put the fault back in a scratch
  copy of `webapp/index.html` and run with `E2E_WEBAPP_HTML=<copy>`: the
  phones load that page instead of the server's, with everything else
  (fonts, art, the API) still real.

## Adding a scenario

```python
def test_something_two_people_do(server):
    alice = server.player("Alice", paid=True)   # bought access via a signed webhook
    bob = server.player("Bob")                  # did not
    code = alice.ok("POST", "/api/compat")["code"]
    bob.ok("POST", f"/api/compat/{code}/join")
    assert bob.status("GET", "/api/compat/NOPE") == 404
```

`ok()` requires a 200 and returns the body; `status()` returns the code;
`call()` returns the response. A 5xx fails the test wherever it happens.
When a rule changes, change the fuzzer's model in `test_duo_fuzz.py` with it:
the model *is* the executable statement of the rules.
