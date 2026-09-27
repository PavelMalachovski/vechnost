"""Tests for the compatibility test's content and scoring."""

import random

import pytest

from vechnost_bot.compat import (
    QUESTIONS_PER_SPHERE,
    SPHERE_COUNT,
    TOTAL_QUESTIONS,
    _content,
    build_result,
    load_spheres,
    scale_labels,
)
from vechnost_bot.i18n import Language

SPHERE_IDS = [
    "values", "money", "communication", "intimacy",
    "home", "trust", "social", "empathy",
]


def test_content_loads_with_the_authored_shape():
    spheres = load_spheres(Language.RUSSIAN)
    assert [s.id for s in spheres] == SPHERE_IDS
    assert len(spheres) == SPHERE_COUNT
    for sphere in spheres:
        assert len(sphere.questions) == QUESTIONS_PER_SPHERE
        assert all(q.strip() for q in sphere.questions)
        assert sphere.title.strip()
        assert sphere.synergy.strip()
        assert sphere.imbalance.strip()
        assert sphere.crisis.strip()


def test_forty_questions_and_no_duplicates():
    flat = [q for s in load_spheres(Language.RUSSIAN) for q in s.questions]
    assert len(flat) == TOTAL_QUESTIONS == 40
    assert len(set(flat)) == 40


def test_five_scale_labels():
    labels = scale_labels(Language.RUSSIAN)
    assert len(labels) == 5
    assert all(label.strip() for label in labels)


def test_perfect_agreement_is_100_percent_and_all_strengths():
    result = build_result([5] * 40, [5] * 40)
    assert result.percent == 100
    assert all(s.zone == "strength" for s in result.spheres)
    assert result.divergent_all == []
    assert result.critical_blocks == []
    assert result.strengths_fallback is None
    assert [s.id for s in result.strengths] == SPHERE_IDS


def test_total_disagreement_is_zero_percent_and_all_crisis():
    result = build_result([1] * 40, [1] * 40)
    assert result.percent == 0
    assert all(s.zone == "crisis" for s in result.spheres)
    assert len(result.critical_blocks) == 8
    assert result.strengths == []
    assert result.strengths_fallback is not None


def test_gap_of_two_is_growth_and_not_divergent():
    """5 vs 3 throughout is the spec's example of Зона роста, not a talking point."""
    result = build_result([5] * 40, [3] * 40)
    assert all(s.zone == "growth" for s in result.spheres)
    assert result.divergent_all == []


def test_gap_of_three_is_divergent_but_not_crisis():
    a = [4] * 40
    b = [4] * 40
    b[0] = 1                      # question 1, gap of 3
    result = build_result(a, b)
    assert result.spheres[0].zone == "growth"
    assert result.divergent_all == [1]
    assert result.spheres[0].divergent == [1]


def test_single_gap_of_four_makes_the_sphere_critical():
    a = [5] * 40
    b = [5] * 40
    b[2] = 1                      # question 3, gap of 4
    result = build_result(a, b)
    assert result.spheres[0].zone == "crisis"
    assert result.spheres[1].zone == "strength"
    assert 3 in result.divergent_all


@pytest.mark.parametrize(
    "value_a,value_b,expected",
    [
        (2, 2, "crisis"),     # both below 3
        (2, 3, "growth"),     # only one below 3 — not a crisis
        (3, 3, "growth"),     # 3.0 is the boundary and does not trip it
        (4, 4, "strength"),
    ],
)
def test_zone_boundaries(value_a, value_b, expected):
    a = [value_a] * 5 + [4] * 35
    b = [value_b] * 5 + [4] * 35
    assert build_result(a, b).spheres[0].zone == expected


def test_average_just_under_three_is_a_crisis():
    """2.8 is "below 3" as much as 2 is — the rule is the average, not the label."""
    a = [3, 3, 3, 3, 2] + [4] * 35     # avg 2.8
    b = [3, 3, 3, 2, 2] + [4] * 35     # avg 2.6
    assert build_result(a, b).spheres[0].zone == "crisis"


def test_verdict_text_matches_the_zone():
    spheres = load_spheres(Language.RUSSIAN)
    strong = build_result([5] * 40, [5] * 40)
    assert strong.spheres[0].verdict == spheres[0].synergy
    weak = build_result([1] * 40, [1] * 40)
    assert weak.spheres[0].verdict == spheres[0].crisis


def test_question_numbers_are_one_based_and_global():
    """Sphere 8's questions are numbered 36-40, not 1-5."""
    a = [4] * 40
    b = [4] * 40
    b[39] = 1                     # last question overall
    result = build_result(a, b)
    assert result.divergent_all == [40]
    assert result.spheres[7].divergent == [40]


def test_divergent_questions_carry_their_texts():
    """«Обсудите вопросы №12, 14» is not actionable when neither partner
    remembers what question 12 asked. The result carries the text of every
    divergent question, keyed by its global number — texts only, no answers."""
    a = [4] * 40
    b = [4] * 40
    b[0] = 1                      # question 1
    b[39] = 1                     # question 40
    result = build_result(a, b)
    flat = [q for s in load_spheres(Language.RUSSIAN) for q in s.questions]
    assert set(result.questions) == {1, 40}
    assert result.questions[1] == flat[0]
    assert result.questions[40] == flat[39]


def test_no_divergence_means_no_question_texts():
    assert build_result([5] * 40, [5] * 40).questions == {}


def test_recommendation_lists_the_divergent_numbers():
    a = [4] * 40
    b = [4] * 40
    b[0] = 1
    b[39] = 1
    result = build_result(a, b)
    assert "1" in result.recommendation
    assert "40" in result.recommendation


def test_attention_carries_every_non_strength_sphere_with_a_framing():
    result = build_result([2] * 40, [2] * 40)
    assert [e.sphere.id for e in result.attention] == SPHERE_IDS
    for entry in result.attention:
        assert entry.framing.strip()
        assert entry.sphere.zone == "crisis"


def test_a_divergent_question_is_framed_as_a_gap_even_when_both_are_low():
    """The framing reads only what the result shows. Both averages under 3
    used to win over a divergent question, and so told a partner under 3
    that the other was under 3 too - on a sphere whose zone and divergent
    question would equally fit two high averages and one gap of four.
    The gap framing stays true: a divergent question always has one
    partner at 4 or 5 and the other at 1 or 2."""
    a = [2, 2, 2, 2, 2] + [5] * 35     # sphere 1 avg 2.0
    b = [2, 2, 2, 2, 5] + [5] * 35     # sphere 1 avg 2.6, question 5 gap of 3
    result = build_result(a, b)
    sphere_1 = next(e for e in result.attention if e.sphere.id == "values")
    assert sphere_1.sphere.zone == "crisis"
    assert sphere_1.sphere.divergent == [5]
    framings = _content(Language.RUSSIAN)["framings"]
    assert sphere_1.framing == framings["gap"]


def test_both_low_framing_only_where_the_zone_already_says_so():
    """A crisis with no divergent question can only be two averages under
    3, so there the framing adds nothing a partner could not work out."""
    a = [2, 3, 2, 2, 2] + [5] * 35     # sphere 1 avg 2.2
    b = [3, 2, 2, 1, 2] + [5] * 35     # sphere 1 avg 2.0, no gap >= 3
    result = build_result(a, b)
    sphere_1 = next(e for e in result.attention if e.sphere.id == "values")
    assert sphere_1.sphere.zone == "crisis"
    assert sphere_1.sphere.divergent == []
    framings = _content(Language.RUSSIAN)["framings"]
    assert sphere_1.framing == framings["both_low"]


def test_gap_framing_is_used_when_divergence_alone_put_it_there():
    """A sphere with at least one average at or above 3 that still lands in
    attention got there through disagreement, not shared low scores."""
    a = [4, 4, 4, 4, 1] + [5] * 35     # sphere 1 avg 3.4, question 5 gap of 3
    b = [4, 4, 4, 4, 4] + [5] * 35     # sphere 1 avg 4.0
    result = build_result(a, b)
    sphere_1 = next(e for e in result.attention if e.sphere.id == "values")
    assert sphere_1.sphere.divergent == [5]
    framings = _content(Language.RUSSIAN)["framings"]
    assert sphere_1.framing == framings["gap"]
    assert sphere_1.framing != framings["both_low"]


def test_no_framing_when_neither_condition_applies():
    """The attention block holds every sphere outside the strength zone, so
    a growth sphere with no divergent question lands here too. There is
    nothing true to say about why, so framing must be None rather than
    defaulting to "gap"."""
    a = [3, 4, 3, 4, 3] + [5] * 35     # sphere 1 avg 3.4
    b = [4, 3, 4, 4, 3] + [5] * 35     # sphere 1 avg 3.6, no gap >= 3
    result = build_result(a, b)
    sphere_1 = next(e for e in result.attention if e.sphere.id == "values")
    assert sphere_1.sphere.divergent == []
    assert sphere_1.framing is None


def test_all_strengths_leaves_attention_empty():
    """A couple with no sphere outside the strength zone gets no attention
    entries at all — not the two lowest-scoring strengths, nothing."""
    result = build_result([5] * 40, [5] * 40)
    assert result.attention == []


def test_one_growth_sphere_among_strengths_is_the_sole_attention_entry():
    a = [4] * 5 + [5] * 35     # sphere 0: avg 4.0
    b = [3] * 5 + [5] * 35     # sphere 0: avg 3.0, no single gap >= 3 -> growth
    result = build_result(a, b)
    assert result.spheres[0].zone == "growth"
    assert all(s.zone == "strength" for s in result.spheres[1:])
    assert len(result.attention) == 1
    assert result.attention[0].sphere.id == "values"


def test_no_sphere_is_ever_in_both_strengths_and_attention():
    """The invariant a partner actually reads the screen by: a sphere can't
    be labelled both "where you are a team" and "worth talking about" at
    once. Checked over a spread of inputs, not a single lucky case — the
    first three are concrete reproductions of the reported bug (one or two
    growth spheres surrounded by spheres tied at a strength score), which
    reliably fail against the pre-fix "two lowest-scoring, unconditionally"
    logic; the fuzzed batch adds broader coverage on top."""
    concrete_cases = [
        # Exactly the coordinator's report: one sphere avg 3.0, seven at 4.0.
        ([3] * 5 + [4] * 35, [3] * 5 + [4] * 35),
        # Two growth spheres (one both-low, one gap-driven) among six tied
        # strength spheres.
        ([3] * 5 + [4, 4, 4, 4, 1] + [4] * 30, [3] * 5 + [4] * 35),
        # A single narrowly-growth sphere (avg just under 4, no divergence)
        # among seven spheres exactly tied at a strength score.
        ([3, 4, 3, 4, 3] + [4] * 35, [4, 3, 4, 4, 3] + [4] * 35),
    ]
    rng = random.Random(20260801)
    fuzzed_cases = [
        (
            [rng.randint(1, 5) for _ in range(TOTAL_QUESTIONS)],
            [rng.randint(1, 5) for _ in range(TOTAL_QUESTIONS)],
        )
        for _ in range(200)
    ]
    for a, b in concrete_cases + fuzzed_cases:
        result = build_result(a, b)
        strength_ids = {s.id for s in result.strengths}
        attention_ids = {e.sphere.id for e in result.attention}
        assert not (strength_ids & attention_ids), (a, b)


def test_lists_follow_the_authored_order_not_the_score():
    """Ranking by score was the leak one comparison at a time: a partner
    who knows their own averages learns from the order which of the
    other's is higher. Here the best sphere is the last one authored, and
    the worst one comes after a better one."""
    a = [4] * 5 + [3] * 5 + [1] * 5 + [4] * 20 + [5] * 5
    b = [4] * 5 + [4] * 5 + [2] * 5 + [4] * 20 + [5] * 5
    result = build_result(a, b)
    assert [s.id for s in result.strengths] == [
        "values", "intimacy", "home", "trust", "social", "empathy",
    ]
    # money is growth (3.0 and 4.0), communication a crisis (1.0 and 2.0).
    assert [e.sphere.id for e in result.attention] == ["money", "communication"]
    assert [e.sphere.zone for e in result.attention] == ["growth", "crisis"]


def test_everything_but_the_percent_follows_from_zones_and_divergence():
    """The property B-25 asked for, on a pair a partner could otherwise tell
    apart: sphere 1 is a crisis with question 5 divergent both times, once
    from two low averages and once from two high ones and a gap of four."""
    both_low = build_result(
        [2, 2, 2, 2, 2] + [5] * 35,
        [2, 2, 2, 2, 5] + [5] * 35,
    )
    one_gap = build_result(
        [5, 5, 5, 5, 1] + [5] * 35,
        [5, 5, 5, 5, 5] + [5] * 35,
    )
    assert both_low.percent != one_gap.percent
    assert both_low.model_dump(exclude={"percent"}) == one_gap.model_dump(
        exclude={"percent"}
    )


def test_lists_and_framings_are_a_function_of_the_public_result():
    """Over a spread of inputs: strengths and attention are exactly the
    spheres of their zones in authored order, and the framing is decided by
    the zone and the divergent questions alone."""
    framings = _content(Language.RUSSIAN)["framings"]
    rng = random.Random(20260927)
    for _ in range(300):
        a = [rng.randint(1, 5) for _ in range(TOTAL_QUESTIONS)]
        b = [rng.randint(1, 5) for _ in range(TOTAL_QUESTIONS)]
        result = build_result(a, b)
        assert result.strengths == [
            s for s in result.spheres if s.zone == "strength"
        ], (a, b)
        assert [e.sphere for e in result.attention] == [
            s for s in result.spheres if s.zone != "strength"
        ], (a, b)
        for entry in result.attention:
            expected = (
                framings["gap"] if entry.sphere.divergent
                else framings["both_low"] if entry.sphere.zone == "crisis"
                else None
            )
            assert entry.framing == expected, (a, b)


def test_result_never_contains_raw_answers():
    """The whole feature's privacy promise, asserted on the serialized model."""
    a = [1, 2, 3, 4, 5] * 8
    b = [5, 4, 3, 2, 1] * 8
    dumped = build_result(a, b).model_dump_json()
    assert "answers" not in dumped


def test_wrong_length_input_raises():
    with pytest.raises(ValueError):
        build_result([5] * 39, [5] * 40)
