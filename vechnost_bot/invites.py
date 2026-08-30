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

from .config import settings

# The three doors, and the app screen each one opens. The prefix is what
# travels inside the link; the screen is what `?screen=` says when the bot
# hands the tap on to the Mini App.
INVITE_SCREENS: dict[str, str] = {
    "s69": "steps69",
    "cmp": "compat",
    "duo": "coop",
}

# Codes are six characters of `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`. Nothing
# else may travel in a link, so a hostile `?start=` cannot smuggle a path.
_CODE_ALPHABET = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def _valid_code(code: str) -> bool:
    return len(code) == 6 and set(code) <= _CODE_ALPHABET


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
