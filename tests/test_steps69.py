"""The board itself: 69 cells, the portals, the dice and the Joker."""

import os
import random
from collections import Counter

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot import steps69
from vechnost_bot.i18n import Language

# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

def test_the_board_is_sixty_nine_cells_numbered_in_order():
    cells = steps69.load_cells()
    assert len(cells) == steps69.BOARD_SIZE == 69
    assert [c.id for c in cells] == list(range(1, 70))


def test_the_board_opens_on_a_start_and_closes_on_the_finale():
    cells = steps69.load_cells()
    assert cells[0].kind == "start"
    assert cells[-1].kind == "final"


def test_the_portals_are_the_ones_the_brief_declares():
    """Ladders and snakes are read off the cells, so a cell rewritten without
    its portal would show up here rather than at a couple's expense."""
    assert steps69.ladders() == {4: 18, 22: 40, 42: 60, 65: 68}
    assert steps69.snakes() == {13: 2, 35: 20, 55: 38}


def test_ladders_go_up_and_snakes_go_down():
    for start, end in steps69.ladders().items():
        assert end > start, f"ladder {start} goes down to {end}"
    for start, end in steps69.snakes().items():
        assert end < start, f"snake {start} goes up to {end}"


def test_no_portal_lands_on_another_portal():
    """`resolve_move` fires a portal once and does not loop. That is only
    safe because no target is itself a portal; if one ever were, a piece
    could bounce between two cells forever."""
    portals = steps69.portals()
    for start, end in portals.items():
        assert end not in portals, f"{start} lands on portal {end}"


def test_every_portal_target_is_on_the_board():
    for start, end in steps69.portals().items():
        assert 1 <= end <= steps69.BOARD_SIZE, f"{start} -> {end}"


def test_there_are_three_jokers_and_they_are_spread_across_the_board():
    jokers = [c.id for c in steps69.load_cells() if c.kind == "joker"]
    assert jokers == [9, 29, 50]
    assert {steps69.stage_of(j) for j in jokers} == {"tender", "drive", "ecstasy"}


def test_every_secret_cell_carries_both_halves():
    """A secret with no partner line leaves the other player staring at a
    blank screen for the length of the task."""
    for c in steps69.load_cells():
        if c.kind == "secret":
            assert c.secret, f"cell {c.id} has no secret"
            assert c.partner, f"cell {c.id} has no partner line"


def test_only_secret_cells_carry_secrets():
    for c in steps69.load_cells():
        if c.kind != "secret":
            assert c.secret is None, f"cell {c.id} is a {c.kind} with a secret"


def test_every_cell_a_player_can_stand_on_says_something():
    for c in steps69.load_cells():
        assert c.title.strip(), f"cell {c.id} has no title"
        if c.kind not in ("joker",):
            assert c.text.strip(), f"cell {c.id} has no text"


def test_the_blocks_tile_the_board_without_gaps_or_overlaps():
    blocks = steps69.load_blocks()
    covered = [n for b in blocks for n in range(b.first, b.last + 1)]
    assert covered == list(range(1, 70))


def test_milestones_land_on_every_tenth_ordinary_cell():
    """Every tenth cell asks the pair to say what is turning them on. Cell 50
    is a Joker, and stacking a drawn task on a milestone prompt buries both,
    so the rule is deliberately "ordinary cells only"."""
    milestones = [c.id for c in steps69.load_cells() if c.is_milestone]
    assert milestones == [10, 20, 30, 40, 60]
    assert steps69.cell(50).kind == "joker"


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------

def test_an_ordinary_roll_just_advances():
    move = steps69.resolve_move(1, 2)
    assert (move.landed, move.position, move.event) == (3, 3, None)


def test_landing_on_a_ladder_carries_the_piece_up():
    move = steps69.resolve_move(3, 1)  # onto cell 4
    assert move.landed == 4
    assert move.position == 18
    assert move.event == "ladder"
    assert move.message


def test_landing_on_a_snake_carries_the_piece_down():
    move = steps69.resolve_move(12, 1)  # onto cell 13
    assert move.landed == 13
    assert move.position == 2
    assert move.event == "snake"


def test_overshooting_the_end_lands_on_sixty_nine_rather_than_bouncing():
    """A pair mid-sex should not be sent backwards on a technicality."""
    move = steps69.resolve_move(68, 6)
    assert move.landed == move.position == 69
    assert move.event is None


def test_a_roll_that_hits_sixty_nine_exactly_is_the_same_square():
    assert steps69.resolve_move(63, 6).position == 69


def test_a_move_off_the_board_or_an_impossible_die_is_refused():
    with pytest.raises(ValueError):
        steps69.resolve_move(0, 3)
    with pytest.raises(ValueError):
        steps69.resolve_move(70, 3)
    with pytest.raises(ValueError):
        steps69.resolve_move(5, 7)
    with pytest.raises(ValueError):
        steps69.resolve_move(5, 0)


def test_every_reachable_square_resolves():
    """Brute force: no start/roll pair may raise or leave the board."""
    for start in range(1, 70):
        for roll in range(1, 7):
            move = steps69.resolve_move(start, roll)
            assert 1 <= move.position <= 69
            assert not steps69.cell(move.position).is_portal


def test_the_die_only_ever_shows_one_to_six():
    rng = random.Random(0)
    rolls = Counter(steps69.roll_dice(rng) for _ in range(600))
    assert set(rolls) == {1, 2, 3, 4, 5, 6}


# ---------------------------------------------------------------------------
# The Joker
# ---------------------------------------------------------------------------

def test_the_board_splits_into_three_stages():
    assert steps69.stage_of(1) == "tender"
    assert steps69.stage_of(23) == "tender"
    assert steps69.stage_of(24) == "drive"
    assert steps69.stage_of(46) == "drive"
    assert steps69.stage_of(47) == "ecstasy"
    assert steps69.stage_of(69) == "ecstasy"


def test_a_pair_carried_by_the_ladders_counts_as_rushing():
    assert steps69.is_rushing(50, 6) is True     # ~8 cells a roll
    assert steps69.is_rushing(50, 20) is False   # ~2.5 cells a roll
    assert steps69.is_rushing(1, 0) is False     # nobody has rolled yet


def test_a_rushing_pair_gets_slowed_down_wherever_they_are_standing():
    """The tempo rule beats the stage rule, which is the whole point: a pair
    who reached the last third in six rolls have not earned an ecstasy task,
    they have skipped everything that makes one land."""
    rng = random.Random(1)
    fast = steps69.pick_joker(50, 6, rng=rng)
    slow = steps69.pick_joker(50, 20, rng=rng)
    assert fast in steps69.load_jokers()["tender"]
    assert slow in steps69.load_jokers()["ecstasy"]


def test_a_joker_task_is_not_dealt_twice_in_one_game():
    rng = random.Random(2)
    used: list[str] = []
    for _ in range(len(steps69.load_jokers()["tender"])):
        task = steps69.pick_joker(9, 20, used=used, rng=rng)
        assert task.id not in used
        used.append(task.id)


def test_an_exhausted_pool_repeats_rather_than_failing():
    spent = [t.id for t in steps69.load_jokers()["tender"]]
    task = steps69.pick_joker(9, 20, used=spent)
    assert task.id in spent


def test_joker_tasks_are_not_on_the_board():
    """The brief asks the Joker for "задание, которого нет на основной карте"."""
    board_titles = {c.title.casefold() for c in steps69.load_cells()}
    for tasks in steps69.load_jokers().values():
        for task in tasks:
            assert task.title.casefold() not in board_titles


def test_joker_task_ids_are_unique_across_the_pools():
    ids = [t.id for tasks in steps69.load_jokers().values() for t in tasks]
    assert len(ids) == len(set(ids))


def test_a_joker_task_can_be_found_by_id():
    task = steps69.load_jokers()["drive"][0]
    assert steps69.joker_task(task.id) == task
    assert steps69.joker_task("nope") is None


# ---------------------------------------------------------------------------
# What each player is allowed to see
# ---------------------------------------------------------------------------

def test_the_map_carries_titles_and_arrows_but_no_instructions():
    """The board is the paid content. Titles make it legible; the text of a
    square you have not reached would let a client read the deck ahead."""
    view = steps69.board_view()
    assert view["size"] == 69
    assert len(view["cells"]) == 69
    flat = repr(view)
    for c in steps69.load_cells():
        assert c.text not in flat or not c.text
        if c.secret:
            assert c.secret not in flat
    assert view["cells"][3]["to"] == 18


def test_the_mover_reads_the_secret_and_the_partner_does_not():
    secret_cell = next(c for c in steps69.load_cells() if c.kind == "secret")
    mover = steps69.cell_view(secret_cell.id, "mover")
    partner = steps69.cell_view(secret_cell.id, "partner")

    assert mover["secret"] == secret_cell.secret
    assert mover["partner"] is None
    assert partner["secret"] is None
    assert partner["partner"] == secret_cell.partner


def test_one_phone_gets_both_halves():
    """A solo game has no second device to withhold anything from."""
    secret_cell = next(c for c in steps69.load_cells() if c.kind == "secret")
    shared = steps69.cell_view(secret_cell.id, "shared")
    assert shared["secret"] and shared["partner"]


def test_an_unknown_audience_is_refused():
    with pytest.raises(ValueError):
        steps69.cell_view(1, "everyone")


def test_a_joker_cell_carries_the_task_the_server_already_drew():
    task = steps69.load_jokers()["tender"][0]
    view = steps69.cell_view(9, "mover", joker_task_id=task.id)
    assert view["joker"]["text"] == task.text

    # Nothing drawn yet: the cell is still legible, the task is simply absent.
    assert steps69.cell_view(9, "mover")["joker"] is None


def test_the_last_cell_carries_the_finale_and_its_choices():
    view = steps69.cell_view(69, "shared")
    choices = view["finale"]["choices"]
    assert {c["id"] for c in choices} == {"sync", "taking_turns"}
    assert view["finale"]["outro"]


def test_a_milestone_cell_carries_its_prompt_and_others_do_not():
    assert steps69.cell_view(10, "shared")["milestone_text"]
    assert steps69.cell_view(11, "shared")["milestone_text"] is None


def test_asking_for_a_cell_off_the_board_raises():
    with pytest.raises(IndexError):
        steps69.cell(0)
    with pytest.raises(IndexError):
        steps69.cell(70)


def test_a_retired_language_code_reads_as_russian():
    assert steps69.load_cells(Language.coerce("en")) == steps69.load_cells()
