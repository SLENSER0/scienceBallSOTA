"""Tests for the absence-claim abstention cutoff selector (§25.15)."""

from __future__ import annotations

from kg_eval.absence_abstention_policy import AbstentionPolicy, select_cutoff

RECORDS = [(0.9, True), (0.8, True), (0.7, False), (0.6, True)]


def test_zero_budget_accepts_high_confidence_prefix() -> None:
    policy = select_cutoff(RECORDS, max_false_gap_rate=0.0)
    assert policy.n_accepted == 2
    assert policy.coverage == 0.5
    assert policy.false_gap_rate == 0.0
    assert policy.cutoff == 0.8


def test_full_budget_accepts_everything() -> None:
    policy = select_cutoff(RECORDS, max_false_gap_rate=1.0)
    assert policy.n_accepted == 4
    assert policy.coverage == 1.0
    assert policy.cutoff == 0.6


def test_false_gap_rate_equals_errors_over_accepted() -> None:
    # Budget 0.25 admits the length-4 prefix (1 error / 4 = 0.25 <= 0.25).
    policy = select_cutoff(RECORDS, max_false_gap_rate=0.25)
    assert policy.n_accepted == 4
    assert policy.false_gap_rate == 1 / 4


def test_coverage_monotonic_in_budget() -> None:
    budgets = [0.0, 0.1, 0.2, 0.25, 0.34, 0.5, 1.0]
    coverages = [select_cutoff(RECORDS, b).coverage for b in budgets]
    assert coverages == sorted(coverages)


def test_empty_records_no_division_error() -> None:
    policy = select_cutoff([], max_false_gap_rate=0.5)
    assert policy.n_accepted == 0
    assert policy.coverage == 0.0
    assert policy.false_gap_rate == 0.0
    assert policy.cutoff == 1.0


def test_budget_rejecting_everything_returns_unit_cutoff() -> None:
    # Every prefix starts with a wrong claim, so no prefix meets a 0.0 budget.
    records = [(0.9, False), (0.8, False), (0.7, True)]
    policy = select_cutoff(records, max_false_gap_rate=0.0)
    assert policy.n_accepted == 0
    assert policy.cutoff == 1.0
    assert policy.coverage == 0.0
    assert policy.false_gap_rate == 0.0


def test_sorted_by_confidence_not_input_order() -> None:
    # Unsorted input: the single most-confident record is a correct claim.
    records = [(0.5, False), (0.95, True), (0.6, False)]
    policy = select_cutoff(records, max_false_gap_rate=0.0)
    assert policy.n_accepted == 1
    assert policy.cutoff == 0.95


def test_frozen_and_as_dict() -> None:
    policy = select_cutoff(RECORDS, max_false_gap_rate=0.0)
    assert isinstance(policy, AbstentionPolicy)
    assert policy.as_dict() == {
        "cutoff": 0.8,
        "coverage": 0.5,
        "false_gap_rate": 0.0,
        "n_accepted": 2,
    }
