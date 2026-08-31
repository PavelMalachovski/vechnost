"""Environment defaults for the test suite.

`vechnost_bot.config` builds its `Settings` at import time and
`TELEGRAM_BOT_TOKEN` has no default, so importing any module of the package
without one raises before a single test runs. A developer with a `.env` never
noticed; CI, which has no `.env` and no secret, could not collect the suite at
all.

pytest imports the rootdir conftest before `tests/conftest.py` and before any
test module, so this is the one place the variable can be set early enough.
Only fill in what is missing: a real environment (or a `.env`) still wins, and
`test_config.py` clears `os.environ` where it means to test the absence.
"""

import os

# Shaped like a real token so python-telegram-bot's own format check passes;
# it addresses no bot, and nothing in the suite reaches the network.
os.environ.setdefault(
    "TELEGRAM_BOT_TOKEN", "123456:AAHtest-token-for-the-suite-000000000000"
)
