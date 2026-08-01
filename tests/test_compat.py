"""Tests for the compatibility test's content and scoring."""

import pytest

from vechnost_bot.compat import (
    QUESTIONS_PER_SPHERE,
    SPHERE_COUNT,
    TOTAL_QUESTIONS,
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
    assert len(result.strengths) == 3


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


def test_recommendation_lists_the_divergent_numbers():
    a = [4] * 40
    b = [4] * 40
    b[0] = 1
    b[39] = 1
    result = build_result(a, b)
    assert "1" in result.recommendation
    assert "40" in result.recommendation


def test_attention_carries_two_spheres_with_a_framing():
    result = build_result([2] * 40, [2] * 40)
    assert len(result.attention) == 2
    for entry in result.attention:
        assert entry.framing.strip()
        assert entry.sphere.zone == "crisis"


def test_result_never_contains_raw_answers():
    """The whole feature's privacy promise, asserted on the serialized model."""
    a = [1, 2, 3, 4, 5] * 8
    b = [5, 4, 3, 2, 1] * 8
    dumped = build_result(a, b).model_dump_json()
    assert "answers" not in dumped


def test_wrong_length_input_raises():
    with pytest.raises(ValueError):
        build_result([5] * 39, [5] * 40)
