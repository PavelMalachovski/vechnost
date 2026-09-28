"""Where a line may not break: after a short word, and before a dash.

A one-letter preposition left at the end of a line («в», «с», «к», «и»)
reads as if the sentence stopped there, and a dash at the start of a line
reads as a new item in a list (audit D-31). Russian typesetting keeps a
short word with the word after it and a dash with the word before it; this
is that rule, in one place, for both front-ends:

- `nbsp` glues with no-break spaces, for text a client lays out itself: a
  message the bot sends, which Telegram wraps. The Mini App applies the
  same rule (`bindShortWords` in webapp/index.html, which
  tests/test_typography.py holds to this one).
- `units` groups words for the renderer, which wraps a card itself: a line
  may break between two units and never inside one.

A domain module: no FastAPI, no python-telegram-bot.
"""

import re

# Three-letter prepositions that hang just as badly as the short ones.
PREPOSITIONS = frozenset({"без", "для", "над", "под", "при", "про", "изо", "обо", "ото"})

_LETTERS = "A-Za-zА-Яа-яЁё"
_DASHES = "–—"

# A word that keeps the next one: one or two letters, a listed preposition,
# or a number of up to three digits («69 ступеней», «5 карт»).
_SHORT = re.compile(rf"^(?:[{_LETTERS}]{{1,2}}|[0-9]{{1,3}})$")
# A short word at the start of the text or after anything but a letter or a
# digit, with the plain space that follows it. The character before the
# word is captured, not looked behind at: the Mini App runs the same pattern
# in JavaScript, and Telegram's WebView on older iPhones has no lookbehind.
_SHORT_THEN_SPACE = re.compile(rf"(^|[^{_LETTERS}0-9])([{_LETTERS}]{{1,3}}|[0-9]{{1,3}}) (?=\S)")
_SPACE_THEN_DASH = re.compile(rf" (?=[{_DASHES}](?:\s|$))")
_TAG = re.compile(r"(<[^>]*>)")

NBSP = "\u00a0"


def binds(word: str) -> bool:
    """Whether `word` stays on the line of the word after it."""
    bare = word.strip("«»\"'(„“")
    return bool(_SHORT.match(bare)) or bare.lower() in PREPOSITIONS


def _glue(text: str) -> str:
    def keep(match: re.Match[str]) -> str:
        lead, word = match.group(1), match.group(2)
        return lead + word + (NBSP if binds(word) else " ")

    # Twice: in «а и в доме» the match for «а» takes the space «и» needs as
    # its lead, so one pass binds every other short word and the second the
    # rest.
    for _ in range(2):
        text = _SHORT_THEN_SPACE.sub(keep, text)
    return _SPACE_THEN_DASH.sub(NBSP, text)


def nbsp(text: str) -> str:
    """`text` with a no-break space after every short word and before every
    dash. HTML tags are left alone: `<a href=...>` has a one-letter word in
    it too."""
    return "".join(part if _TAG.fullmatch(part) else _glue(part) for part in _TAG.split(text))


def units(text: str) -> list[str]:
    """The words of `text`, grouped so that a short word travels with the
    word after it and a dash with the word before it. Joined by plain
    spaces: the renderer draws them, and only measures where to break."""
    grouped: list[str] = []
    for word in text.split():
        if grouped and (binds(grouped[-1].rsplit(" ", 1)[-1]) or word[0] in _DASHES):
            grouped[-1] += " " + word
        else:
            grouped.append(word)
    return grouped
