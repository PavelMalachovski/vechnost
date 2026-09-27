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
| Browsers | `browser/test_two_phones.py` | Two Chromium phones driving the Mini App UI: the invite link one screen shows opens the other, the waiting phone catches up by itself, no deal leaks to the wrong screen | CI (`E2E_BROWSER=1`) |

## Running it

```bash
pytest tests/e2e -n0                        # scenarios, bot, a short fuzz (~15 s)
E2E_FUZZ_EXAMPLES=400 E2E_FUZZ_STEPS=100 \
  pytest tests/e2e/test_duo_fuzz.py -n0 -s  # the nightly fuzz (~13 min), prints what it reached

pip install -e ".[dev,e2e]" && python -m playwright install chromium
E2E_BROWSER=1 pytest tests/e2e/browser -n0  # two phones in Chromium (~1 min)
```

Screenshots of every browser step, a Playwright trace of each phone when a
test fails, and `fuzz_coverage.json` go to `E2E_REPORT_DIR` (default
`./e2e-report`, git-ignored).

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
