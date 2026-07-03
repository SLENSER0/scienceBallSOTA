"""Tests for the crosswalk golden regression evaluator (§20.13)."""

from __future__ import annotations

from kg_eval.crosswalk_golden import (
    CrosswalkGoldenCase,
    CrosswalkGoldenReport,
    evaluate_crosswalk,
)


def _cases() -> list[CrosswalkGoldenCase]:
    return [
        CrosswalkGoldenCase("elabftw", "a", "c:1"),
        CrosswalkGoldenCase("openbis", "b", "c:2"),
        CrosswalkGoldenCase("mp", "d", "c:3"),
    ]


def test_correct_incorrect_missing_counts() -> None:
    pred = {
        ("elabftw", "a"): "c:1",
        ("openbis", "b"): "c:9",
        ("mp", "d"): "c:3",
    }
    rep = evaluate_crosswalk(_cases(), pred)
    assert rep.correct == 2
    assert rep.incorrect == 1
    assert rep.missing == 0
    assert abs(rep.accuracy - 2 / 3) < 1e-9


def test_mismatch_tuple_recorded() -> None:
    pred = {
        ("elabftw", "a"): "c:1",
        ("openbis", "b"): "c:9",
        ("mp", "d"): "c:3",
    }
    rep = evaluate_crosswalk(_cases(), pred)
    assert ("b", "c:2", "c:9") in rep.mismatches


def test_missing_key_increments_missing_not_incorrect() -> None:
    # 'mp'/'d' absent -> counts as missing, not incorrect.
    pred = {
        ("elabftw", "a"): "c:1",
        ("openbis", "b"): "c:2",
    }
    rep = evaluate_crosswalk(_cases(), pred)
    assert rep.missing == 1
    assert rep.incorrect == 0
    assert rep.correct == 2
    assert rep.mismatches == ()


def test_total_partitions_into_three_buckets() -> None:
    pred = {
        ("elabftw", "a"): "c:1",
        ("openbis", "b"): "c:9",
    }
    rep = evaluate_crosswalk(_cases(), pred)
    assert rep.total == 3
    assert rep.total == rep.correct + rep.incorrect + rep.missing


def test_empty_cases_accuracy_zero() -> None:
    rep = evaluate_crosswalk([], {})
    assert rep.accuracy == 0.0
    assert rep.total == 0
    assert rep.mismatches == ()


def test_all_correct() -> None:
    pred = {
        ("elabftw", "a"): "c:1",
        ("openbis", "b"): "c:2",
        ("mp", "d"): "c:3",
    }
    rep = evaluate_crosswalk(_cases(), pred)
    assert rep.correct == 3
    assert rep.accuracy == 1.0
    assert rep.mismatches == ()


def test_case_as_dict() -> None:
    d = CrosswalkGoldenCase("elabftw", "a", "c:1").as_dict()
    assert d == {"system": "elabftw", "external_id": "a", "expected_canonical": "c:1"}


def test_report_as_dict_has_six_keys() -> None:
    rep = evaluate_crosswalk(_cases(), {("elabftw", "a"): "c:1"})
    d = rep.as_dict()
    assert set(d) == {
        "total",
        "correct",
        "incorrect",
        "missing",
        "accuracy",
        "mismatches",
    }
    assert len(d) == 6


def test_report_is_frozen() -> None:
    rep = CrosswalkGoldenReport(0, 0, 0, 0, 0.0, ())
    try:
        rep.total = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("CrosswalkGoldenReport must be frozen")
