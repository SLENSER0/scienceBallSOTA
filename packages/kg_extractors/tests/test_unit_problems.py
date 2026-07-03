"""Unit/value problem classification + review flags (§7.6)."""

from __future__ import annotations

from kg_extractors.unit_problems import (
    PROBLEM_DIMENSIONLESS_UNIT,
    PROBLEM_MISSING_UNIT,
    PROBLEM_NEGATIVE,
    PROBLEM_OUT_OF_RANGE,
    PROBLEM_UNPARSEABLE_UNIT,
    REVIEW_TASK_KIND,
    SEVERITY_LEVELS,
    ProblemReport,
    classify_problems,
)


def test_value_without_unit_is_missing_unit_gap() -> None:
    """A value with no unit on a unit-bearing property → missing_unit gap (§7.6)."""
    r = classify_problems(300, None, property_id="prop:tds")
    assert r.is_missing_unit_gap is True
    assert PROBLEM_MISSING_UNIT in r.problems
    assert r.severity == "warning"
    assert r.review_task is not None


def test_garbage_unit_is_unparseable_error() -> None:
    """A unit neither policy-allowed nor pint-parseable → unparseable error (§7.6)."""
    r = classify_problems(10, "zorp", property_id=None)
    assert PROBLEM_UNPARSEABLE_UNIT in r.problems
    assert r.severity == "error"
    assert r.is_missing_unit_gap is False
    assert r.review_task is not None


def test_5000_hv_is_out_of_range() -> None:
    """5000 HV exceeds the hard hardness maximum (2000 HV) → out_of_range error (§7.7)."""
    r = classify_problems(5000, "HV", property_id="prop:hardness")
    assert PROBLEM_OUT_OF_RANGE in r.problems
    assert r.severity == "error"
    assert r.is_missing_unit_gap is False


def test_valid_145_hv_is_ok_no_review() -> None:
    """145 HV is a valid, in-range hardness → clean report, no review task (§7.6)."""
    r = classify_problems(145, "HV", property_id="prop:hardness")
    assert r.problems == []
    assert r.severity == "ok"
    assert r.review_task is None
    assert r.is_missing_unit_gap is False


def test_negative_recovery_is_flagged() -> None:
    """A negative recovery (min 0%) → negative_where_nonneg + error (§7.6)."""
    r = classify_problems(-5, "%", property_id="prop:recovery")
    assert PROBLEM_NEGATIVE in r.problems
    assert r.severity == "error"
    assert r.review_task is not None


def test_property_id_none_still_classifies_missing_unit() -> None:
    """Missing-unit is detected even without a property id (§7.6)."""
    r = classify_problems(300, None)  # property_id defaults to None
    assert r.is_missing_unit_gap is True
    assert PROBLEM_MISSING_UNIT in r.problems


def test_review_task_shape() -> None:
    """The review task carries kind/reason/property_id/value/unit (§7.6)."""
    r = classify_problems(250, None, property_id="prop:current_density")
    task = r.review_task
    assert task is not None
    assert set(task.keys()) == {"kind", "reason", "property_id", "value", "unit"}
    assert task["kind"] == REVIEW_TASK_KIND
    assert task["property_id"] == "prop:current_density"
    assert task["value"] == 250
    assert task["unit"] is None
    assert PROBLEM_MISSING_UNIT in str(task["reason"])


def test_severity_ordering() -> None:
    """Outlier (typical<v<hard) → warning; over hard max → error; ranked ok<warn<err."""
    warn = classify_problems(1500, "HV", property_id="prop:hardness")  # 1200<1500<2000
    err = classify_problems(5000, "HV", property_id="prop:hardness")  # 5000>2000
    assert warn.severity == "warning" and err.severity == "error"
    assert SEVERITY_LEVELS.index("ok") < SEVERITY_LEVELS.index("warning")
    assert SEVERITY_LEVELS.index("warning") < SEVERITY_LEVELS.index("error")
    assert SEVERITY_LEVELS.index(warn.severity) < SEVERITY_LEVELS.index(err.severity)


def test_dimensionless_property_with_unit_flagged() -> None:
    """A unit attached to pH (dimensionless) → dimensionless_expected flag (§7.6)."""
    r = classify_problems(7, "mg/L", property_id="prop:ph")
    assert PROBLEM_DIMENSIONLESS_UNIT in r.problems
    assert r.severity == "warning"
    assert r.review_task is not None


def test_ph_missing_unit_is_ok() -> None:
    """A unitless property (pH) with no unit is legitimate — no gap, no problem (§7.6)."""
    r = classify_problems(7, None, property_id="prop:ph")
    assert r.is_missing_unit_gap is False
    assert PROBLEM_MISSING_UNIT not in r.problems
    assert r.problems == []
    assert r.severity == "ok"
    assert r.review_task is None


def test_as_dict_roundtrip() -> None:
    """as_dict exposes the four report fields (§7.6)."""
    r = classify_problems(5000, "HV", property_id="prop:hardness")
    d = r.as_dict()
    assert set(d.keys()) == {"problems", "severity", "review_task", "is_missing_unit_gap"}
    assert d["severity"] == r.severity
    assert d["problems"] == r.problems
    assert isinstance(r, ProblemReport)
