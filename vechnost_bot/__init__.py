"""Vechnost Telegram Bot - A card game for intimate conversations."""

import os

# python-telegram-bot 22 reports a duration - the wait a flood-control
# RetryAfter names among them - as a datetime.timedelta once PTB_TIMEDELTA is
# set, and warns on every read while it is not; its next major version
# answers only in timedelta. Opting in before anything reads one leaves one
# code path today and nothing to change on that upgrade.
os.environ.setdefault("PTB_TIMEDELTA", "true")

__version__ = "1.0.0"
