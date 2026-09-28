"""Reading what the bot and the app say, for a test about the words.

Every message and button keeps a short word with the next one, joined by a
no-break space (vechnost_bot/typography.py, audit D-31). A test about what
a message says compares its words, not where a line may break.
"""


def plain(text: str) -> str:
    """`text` with its no-break spaces read as ordinary spaces."""
    return text.replace(" ", " ")
