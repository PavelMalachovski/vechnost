"""Tests for freemium rules and price formatting."""

from vechnost_bot.freemium import FREE_CARDS_PER_DECK, free_slice, is_index_free
from vechnost_bot.payments.services import format_price


def test_first_cards_are_free():
    for i in range(FREE_CARDS_PER_DECK):
        assert is_index_free(i)


def test_cards_beyond_limit_are_paid():
    assert not is_index_free(FREE_CARDS_PER_DECK)
    assert not is_index_free(100)
    assert not is_index_free(-1)


def test_free_slice_short_deck():
    assert free_slice(["a", "b"]) == ["a", "b"]


def test_free_slice_long_deck():
    items = [str(i) for i in range(30)]
    assert free_slice(items) == ["0", "1", "2", "3", "4"]


def test_format_price_euro_cents():
    assert format_price(499, "eur") == "4,99 €"


def test_format_price_round_amount():
    assert format_price(500, "eur") == "5 €"


def test_format_price_unknown_currency():
    assert format_price(1250, "pln") == "12,50 PLN"
