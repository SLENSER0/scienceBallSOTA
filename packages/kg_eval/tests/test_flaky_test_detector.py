"""Tests for flaky-test detection from repeated run outcomes (§23)."""

from __future__ import annotations

from collections.abc import Mapping

from kg_eval.flaky_test_detector import FlakyReport, FlakyTest, analyze


def _runs(test_id: str, outcomes: list[str]) -> list[Mapping[str, object]]:
    """Build run records for one test from an ordered list of outcomes."""
    return [{"test_id": test_id, "outcome": outcome} for outcome in outcomes]


def test_all_pass_is_not_flaky_flip_rate_zero() -> None:
    """A test that always passes is stable: no fails, no flips."""
    report = analyze(_runs("t_stable", ["pass", "pass", "pass", "pass"]))
    assert isinstance(report, FlakyReport)
    test = report.tests[0]
    assert isinstance(test, FlakyTest)
    assert test.is_flaky is False
    assert test.flip_rate == 0.0
    assert test.passes == 4
    assert test.fails == 0


def test_all_fail_is_not_flaky() -> None:
    """A test that always fails is deterministic (a real failure, not flaky)."""
    report = analyze(_runs("t_broken", ["fail", "fail", "fail"]))
    test = report.tests[0]
    assert test.is_flaky is False
    assert test.flip_rate == 0.0
    assert report.quarantine == ()


def test_mixed_over_four_runs_is_flaky() -> None:
    """One pass and one fail across >= min_runs runs flags the test flaky."""
    report = analyze(_runs("t_mixed", ["pass", "pass", "fail", "pass"]))
    test = report.tests[0]
    assert test.runs == 4
    assert test.is_flaky is True
    # Two transitions (pass->fail, fail->pass) over three gaps.
    assert test.flip_rate == 2.0 / 3.0


def test_alternating_flip_rate_one() -> None:
    """pass, fail, pass, fail flips on every gap -> flip_rate 1.0."""
    report = analyze(_runs("t_alt", ["pass", "fail", "pass", "fail"]))
    test = report.tests[0]
    assert test.flip_rate == 1.0
    assert test.is_flaky is True


def test_two_runs_below_min_runs_not_flaky() -> None:
    """A test with fewer than min_runs runs is not flaky even if it flips."""
    report = analyze(_runs("t_short", ["pass", "fail"]), min_runs=3)
    test = report.tests[0]
    assert test.runs == 2
    assert test.passes == 1
    assert test.fails == 1
    assert test.is_flaky is False
    assert report.quarantine == ()


def test_quarantine_sorted_and_only_flaky() -> None:
    """Quarantine holds only flaky ids, sorted; stable tests are excluded."""
    records: list[Mapping[str, object]] = []
    records += _runs("z_flaky", ["pass", "fail", "pass"])
    records += _runs("a_flaky", ["fail", "pass", "fail"])
    records += _runs("m_stable", ["pass", "pass", "pass"])
    report = analyze(records)
    assert report.quarantine == ("a_flaky", "z_flaky")
    flaky_ids = {t.test_id for t in report.tests if t.is_flaky}
    assert set(report.quarantine) == flaky_ids


def test_passes_plus_fails_equals_runs() -> None:
    """The pass/fail tally always partitions the run count exactly."""
    report = analyze(_runs("t_any", ["pass", "fail", "fail", "pass", "fail"]))
    for test in report.tests:
        assert test.passes + test.fails == test.runs


def test_non_pass_outcome_counts_as_fail() -> None:
    """Any outcome other than 'pass' (e.g. 'error') counts toward fails."""
    report = analyze(_runs("t_err", ["pass", "error", "pass"]))
    test = report.tests[0]
    assert test.passes == 2
    assert test.fails == 1
    assert test.is_flaky is True


def test_as_dict_nests_tests_as_list() -> None:
    """FlakyReport.as_dict exposes tests as a list of per-test dicts."""
    report = analyze(_runs("t_mixed", ["pass", "fail", "pass", "fail"]))
    data = report.as_dict()
    assert isinstance(data["tests"], list)
    assert isinstance(data["quarantine"], list)
    first = data["tests"][0]
    assert first["test_id"] == "t_mixed"
    assert first["flip_rate"] == 1.0
    assert first["is_flaky"] is True


def test_grouping_preserves_first_seen_order() -> None:
    """Interleaved records group per test while keeping first-seen order."""
    records: list[Mapping[str, object]] = [
        {"test_id": "b", "outcome": "pass"},
        {"test_id": "a", "outcome": "fail"},
        {"test_id": "b", "outcome": "fail"},
        {"test_id": "a", "outcome": "fail"},
    ]
    report = analyze(records, min_runs=2)
    assert [t.test_id for t in report.tests] == ["b", "a"]
    b_test = report.tests[0]
    assert b_test.runs == 2
    assert b_test.is_flaky is True
