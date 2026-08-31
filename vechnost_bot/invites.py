"""Invite links: one tap from a partner's chat into the right screen.

Every two-partner feature used to hand the partner a six-character code to
type at the right door, and the three doors take codes from the same
alphabet — a code entered at the wrong one failed confusingly. A link cannot
be entered at the wrong door.

Two link shapes exist, and which one is minted depends on what the bot has
configured:

* `https://t.me/<bot>/<app>?startapp=<param>` opens the Mini App directly,
  one tap, and Telegram hands `<param>` to the page as `start_param`. It
  needs a Mini App short name set in BotFather (`WEBAPP_SHORT_NAME`).
* `https://t.me/<bot>?start=<param>` opens the chat with the bot, which
  replies with a button into the app. Two taps, nothing to configure.

So the direct link is used when it exists and the bot link when it does
not, and an invite works either way. This module imports neither FastAPI nor
python-telegram-bot, so the web API, the bot and the tests all use it.
"""

import secrets

from .config import settings

# The three doors, and the app screen each one opens. The prefix is what
# travels inside the link; the screen is what `?screen=` says when the bot
# hands the tap on to the Mini App.
INVITE_SCREENS: dict[str, str] = {
    "s69": "steps69",
    "cmp": "compat",
    "duo": "coop",
}

# What a code is made of. Nothing else may travel in a link, so a hostile
# `?start=` cannot smuggle a path.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_ALPHABET = set(CODE_ALPHABET)

# Sixteen characters, not six. A code used to be typed by hand at one of
# three doors, so it was kept short; now it only ever travels inside a link,
# and length is free. Six was 32^6, about a billion — enough that a sweep of
# the space needed patience but not enough that it needed luck, and a hit
# handed the attacker a seat in a stranger's game: the couple's compatibility
# answers, or their board. Sixteen is 32^16, about 10^24, which no amount of
# patience reaches.
CODE_LENGTH = 16

# Codes minted before that, still in the database and still in links already
# sent. They stay valid; they simply stop being issued.
LEGACY_CODE_LENGTH = 6


def new_code() -> str:
    """A fresh code. One generator, so three doors cannot drift apart."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def valid_code(code: str) -> bool:
    """Whether this could be one of our codes, new or legacy."""
    return (
        LEGACY_CODE_LENGTH <= len(code) <= CODE_LENGTH
        and set(code) <= _CODE_ALPHABET
    )


# Kept as the private name the module used before `valid_code` was public.
_valid_code = valid_code


def invite_param(kind: str, code: str) -> str:
    """The payload that travels inside a link, e.g. `s69_AB12CD`."""
    if kind not in INVITE_SCREENS:
        raise KeyError(kind)
    return f"{kind}_{code.strip().upper()}"


def invite_url(kind: str, code: str) -> str | None:
    """The link to send a partner, or None when the bot has no username."""
    param = invite_param(kind, code)
    if settings.bot_username and settings.webapp_short_name:
        return (
            f"https://t.me/{settings.bot_username}/"
            f"{settings.webapp_short_name}?startapp={param}"
        )
    if settings.bot_username:
        return f"https://t.me/{settings.bot_username}?start={param}"
    return None


def parse_invite_param(param: str | None) -> tuple[str, str] | None:
    """`(screen, code)` for an invite payload, or None when it isn't one.

    Unknown prefixes and malformed codes come back as None rather than
    raising: `/start` also carries referral and certificate payloads, and a
    stranger can send anything at all.
    """
    if not param or "_" not in param:
        return None
    kind, _, code = param.partition("_")
    code = code.strip().upper()
    if kind not in INVITE_SCREENS or not _valid_code(code):
        return None
    return INVITE_SCREENS[kind], code
