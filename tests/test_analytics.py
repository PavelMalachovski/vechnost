"""The analytics rules that need no server: what may be stored, and how
the /stats report reads when there is little or nothing to report.

The whole path - the bot, the app's reports, the server's own events,
erasure and the report over real rows - is played in
tests/e2e/test_duo_analytics.py.
"""

from datetime import datetime

import pytest

from vechnost_bot import analytics, stats


@pytest.mark.parametrize(
    ("param", "source"),
    [
        (None, None),
        ("", None),
        ("src_tiktok", "tiktok"),
        ("SRC_TikTok", "tiktok"),
        ("src_blogger_anna-2", "blogger_anna-2"),
        ("src_", None),
        ("src_" + "x" * 40, None),
        ("src_has space", None),
        ("ref_ABC123", "ref"),
        ("duo_ABCDEFGHJKMNPQRS", "invite"),
        ("cmp_ABCDEFGHJKMNPQRS", "invite"),
        ("s69_ABCDEFGHJKMNPQRS", "invite"),
        ("activate_VECH-ABCD-EFGH", "gift"),
        ("something_else", None),
    ],
)
def test_an_arrival_names_its_channel_never_its_parameter(param, source):
    assert analytics.arrival_source(param) == source


def test_a_detail_is_one_token_from_the_events_own_list():
    assert analytics.clean_detail("paywall_view", "room") == "room"
    assert analytics.clean_detail("paywall_view", "Бесплатные карты закончились") is None
    assert analytics.clean_detail("deck_open", "Sex::tasks") == "Sex::tasks"
    assert analytics.clean_detail("deck_open", "Sex:9:tasks") is None
    assert analytics.clean_detail("lib_open", "nude_guide") == "nude_guide"
    assert analytics.clean_detail("lib_open", "../../etc") is None
    # Events that carry no detail keep none, whatever is sent.
    assert analytics.clean_detail("room_join", "ABCDEFGHJKMNPQRS") is None
    assert analytics.clean_detail("app_open", "invite") is None


def test_an_unknown_event_is_not_a_row():
    assert analytics.event_row("made_up", 1) is None
    row = analytics.event_row("deck_open", 1, "Acquaintance:1:questions", "TikTok")
    assert (row.name, row.detail, row.source) == ("deck_open", "Acquaintance:1:questions", "tiktok")


def test_the_client_can_only_report_what_it_can_honestly_know():
    assert analytics.CLIENT_EVENTS <= set(analytics.EVENTS)
    for name in ("purchase", "gift_purchase", "refund", "room_join", "compat_done", "s69_join"):
        assert name not in analytics.CLIENT_EVENTS


async def test_a_count_that_cannot_be_written_breaks_nothing(monkeypatch):
    from vechnost_bot.payments import database

    def broken():
        raise RuntimeError("database is down")

    monkeypatch.setattr(database, "get_db", broken)
    await analytics.track("deck_open", 1, "Acquaintance:1:questions")
    await analytics.track_arrival(1, "tiktok")


def test_an_empty_report_reads_as_nothing_yet_not_as_an_error():
    now = datetime(2026, 9, 27, 12, 0)
    report = stats.Report(now=now, windows=[stats.Window(days=7), stats.Window(days=30)])
    text = stats.render(report)
    assert "Новые люди: 0 / 0" in text
    assert "Активация в первый день: – / –" in text
    assert "пока никого" in text
    assert "на 1-й день: –" in text


def test_a_long_tail_of_sources_is_folded():
    now = datetime(2026, 9, 27, 12, 0)
    month = stats.Window(days=30, new_people=10)
    month.sources = [(f"s{i}", 10 - i) for i in range(9)]
    report = stats.Report(now=now, windows=[stats.Window(days=7), month])
    text = stats.render(report)
    assert "s0: 10" in text and "s5: 5" in text
    assert "s6:" not in text
    assert "остальные: 9" in text
