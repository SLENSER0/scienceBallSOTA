"""Tests for selective prediction — risk-coverage curve & AURC (§23.25)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from kg_eval.selective_risk_coverage import (
    CoveragePoint,
    RiskCoverageReport,
    analyze,
    risk_at_coverage,
)

# A perfectly-ordered predictor: high-confidence answers are all correct, and
# the two low-confidence answers are both wrong.
PERFECT = [
    (0.9, True),
    (0.8, True),
    (0.2, False),
    (0.1, False),
]

# Same confidences/labels but ordered so that a wrong answer carries the highest
# confidence — a worse (adversarial) ranking.
RANDOM = [
    (0.9, False),
    (0.8, True),
    (0.2, True),
    (0.1, False),
]


def test_perfect_ordering_zero_risk_at_half_coverage() -> None:
    # Top half of PERFECT is the two correct high-confidence answers.
    assert risk_at_coverage(PERFECT, 0.5) == 0.0


def test_perfect_ordering_has_lower_aurc_than_random() -> None:
    assert analyze(PERFECT).aurc < analyze(RANDOM).aurc


def test_all_correct_gives_zero_aurc_and_full_coverage_risk() -> None:
    report = analyze([(0.9, True), (0.5, True), (0.1, True)])
    assert report.aurc == 0.0
    assert report.risk_at_full_coverage == 0.0


def test_all_wrong_gives_full_coverage_risk_one() -> None:
    report = analyze([(0.9, False), (0.5, False), (0.1, False)])
    assert report.risk_at_full_coverage == 1.0
    # Every prefix is entirely wrong, so AURC is also 1.0.
    assert report.aurc == 1.0


def test_risk_at_coverage_clamps_below_zero_to_single_record() -> None:
    # coverage <= 0 accepts exactly the single most-confident record (correct here).
    assert risk_at_coverage(PERFECT, 0.0) == 0.0
    assert risk_at_coverage(PERFECT, -3.0) == 0.0


def test_risk_at_coverage_clamps_above_one_to_full() -> None:
    # coverage > 1 accepts everything -> overall error rate = 2 wrong / 4.
    assert risk_at_coverage(PERFECT, 1.5) == 0.5
    assert risk_at_coverage(PERFECT, 1.0) == 0.5


def test_risk_at_coverage_ceil_rounds_partial_up() -> None:
    # 0.6 * 4 = 2.4 -> ceil -> accept top 3; top 3 of PERFECT has 1 wrong.
    assert risk_at_coverage(PERFECT, 0.6) == pytest.approx(1 / 3)


def test_ties_in_confidence_are_deterministic_and_stable() -> None:
    # All equal confidence: stable sort keeps input order, so point thresholds and
    # cumulative risks are fully determined by input order.
    records = [(0.5, True), (0.5, False), (0.5, True)]
    first = analyze(records)
    second = analyze(records)
    assert first.as_dict() == second.as_dict()
    # Input order preserved: risks are 0/1, 1/2, 1/3 cumulatively.
    assert [p.risk for p in first.points] == pytest.approx([0.0, 0.5, 1 / 3])


def test_points_has_exactly_n_entries_with_increasing_coverage() -> None:
    report = analyze(PERFECT)
    assert len(report.points) == report.n == 4
    coverages = [p.coverage for p in report.points]
    assert coverages == pytest.approx([0.25, 0.5, 0.75, 1.0])
    assert all(a < b for a, b in pairwise(coverages))


def test_point_thresholds_follow_descending_confidence() -> None:
    report = analyze(PERFECT)
    thresholds = [p.threshold for p in report.points]
    assert thresholds == pytest.approx([0.9, 0.8, 0.2, 0.1])


def test_aurc_matches_hand_computed_mean_of_risks() -> None:
    # PERFECT prefixes: risks 0, 0, 1/3, 2/4 -> mean = (0 + 0 + 1/3 + 0.5) / 4.
    report = analyze(PERFECT)
    expected = (0.0 + 0.0 + (1 / 3) + 0.5) / 4
    assert report.aurc == pytest.approx(expected)


def test_coverage_point_as_dict_round_trips() -> None:
    point = CoveragePoint(coverage=0.5, risk=0.25, threshold=0.8)
    assert point.as_dict() == {"coverage": 0.5, "risk": 0.25, "threshold": 0.8}


def test_report_as_dict_shape() -> None:
    report = analyze(PERFECT)
    payload = report.as_dict()
    assert isinstance(report, RiskCoverageReport)
    assert payload["n"] == 4
    assert isinstance(payload["points"], list)
    assert len(payload["points"]) == 4
    assert payload["points"][0] == {"coverage": 0.25, "risk": 0.0, "threshold": 0.9}


def test_empty_input_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        analyze([])
    with pytest.raises(ValueError):
        risk_at_coverage([], 0.5)
