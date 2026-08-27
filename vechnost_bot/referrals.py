"""Referral links: a code to hand out, and a cheaper price for whoever uses it.

The discount is a second Tribute product, not a coupon: Tribute owns the
price, so the only thing this side can do is decide which of two payment
pages a user is sent to. `REFERRAL_PAYMENT_URL` is that page. With it unset
the codes are still minted and the invitations still recorded, and everyone
simply pays the same as before, which is the right behaviour for a
deployment that has not created the discounted product yet.

Deliberately imports neither FastAPI nor python-telegram-bot, like the other
domain modules, so the bot, the web API and the tests share one implementation
of what a code is and who may claim one.
"""

import hashlib
import logging

from .config import settings

logger = logging.getLogger(__name__)

# Unambiguous on a phone screen and in a spoken link: no 0/O, no 1/I/L.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

PREFIX = "ref_"


def code_from_seed(seed: str) -> str:
    """A code derived from a seed, for minting without a round trip.

    Derived rather than random so a retry after a lost response produces the
    same candidate instead of burning a fresh one, and hashed rather than
    encoded so the code says nothing about the account behind it.
    """
    digest = hashlib.blake2b(seed.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    out = []
    for _ in range(CODE_LENGTH):
        out.append(CODE_ALPHABET[value % len(CODE_ALPHABET)])
        value //= len(CODE_ALPHABET)
    return "".join(out)


def normalize(code: str | None) -> str | None:
    """A code as stored, or None when it could not be one."""
    if not code:
        return None
    cleaned = code.strip().upper()
    if len(cleaned) != CODE_LENGTH:
        return None
    if any(ch not in CODE_ALPHABET for ch in cleaned):
        return None
    return cleaned


def parse_start_param(param: str | None) -> str | None:
    """The code inside a `?start=ref_XXXXXX` deep link, if there is one."""
    if not param or not param.startswith(PREFIX):
        return None
    return normalize(param[len(PREFIX):])


def invite_link(code: str) -> str | None:
    """The link a user shares, or None when the bot's handle is unknown."""
    if not settings.bot_username:
        return None
    return f"https://t.me/{settings.bot_username}?start={PREFIX}{code}"


def discount_available() -> bool:
    """Whether there is actually a cheaper page to send a referred user to."""
    return bool(settings.referral_payment_url)


def payment_url_for(referred: bool) -> str | None:
    """The Tribute page this user should see, or None to fall back."""
    if referred and discount_available():
        return settings.referral_payment_url
    return None
