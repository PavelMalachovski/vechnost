"""Freemium rules shared by the bot and the Mini App API.

The first FREE_CARDS_PER_DECK cards of every deck (each theme/level
questions or tasks list) are free; the rest require payment.
"""

FREE_CARDS_PER_DECK = 5


def is_index_free(index: int) -> bool:
    """True if the card at this 0-based index is part of the free preview."""
    return 0 <= index < FREE_CARDS_PER_DECK


def free_slice(items: list) -> list:
    """The freely available prefix of a deck's items."""
    return list(items[:FREE_CARDS_PER_DECK])


# Library lists (date ideas, couple practices) show a shorter teaser than
# the decks: three items per category is enough to judge the writing.
FREE_LIBRARY_ITEMS_PER_LIST = 3


def free_library_slice(items: list) -> list:
    """The freely available prefix of one Library list."""
    return list(items[:FREE_LIBRARY_ITEMS_PER_LIST])
