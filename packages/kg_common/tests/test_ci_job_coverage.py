"""Tests for required CI job-coverage — тесты покрытия job'ов (§2.10/§2.4)."""

from __future__ import annotations

from kg_common.ci_job_coverage import (
    DEFAULT_REQUIRED_JOBS,
    CIJobReport,
    check_jobs,
)


def test_default_required_jobs_exact_set() -> None:
    """§2.10/§2.4: the mandated floor is exactly these seven jobs."""
    expected = frozenset({"lint", "test", "build", "compose-smoke", "hadolint", "trivy", "dr-test"})
    assert expected == DEFAULT_REQUIRED_JOBS


def test_partial_present_reports_missing_and_not_ok() -> None:
    """Only lint+test present -> 'build' missing, ok is False."""
    report = check_jobs(["lint", "test"])
    assert "build" in report.missing
    assert report.ok is False


def test_full_default_set_is_ok_with_no_missing() -> None:
    """Presenting the entire required set clears missing and passes."""
    report = check_jobs(DEFAULT_REQUIRED_JOBS)
    assert report.missing == ()
    assert report.ok is True


def test_unrecognized_job_lands_in_extra_and_does_not_affect_ok() -> None:
    """A 'foo' job beyond the floor is extra and does not fail the gate."""
    report = check_jobs([*DEFAULT_REQUIRED_JOBS, "foo"])
    assert "foo" in report.extra
    assert report.missing == ()
    assert report.ok is True


def test_present_is_sorted_and_deduplicated() -> None:
    """A repeated job collapses; present tuple comes out sorted."""
    report = check_jobs(["test", "lint", "test"])
    assert report.present == ("lint", "test")


def test_missing_tuple_is_sorted() -> None:
    """With nothing present, all seven required jobs appear sorted."""
    report = check_jobs([])
    assert report.missing == tuple(sorted(DEFAULT_REQUIRED_JOBS))
    assert list(report.missing) == sorted(report.missing)


def test_custom_required_single_job_missing() -> None:
    """check_jobs([], required=['a']).missing == ('a',)."""
    report = check_jobs([], required=["a"])
    assert report.missing == ("a",)
    assert report.ok is False


def test_extra_is_sorted() -> None:
    """Extra jobs beyond a tiny required set come out sorted."""
    report = check_jobs(["z", "a", "m"], required=["a"])
    assert report.extra == ("m", "z")


def test_as_dict_round_trips_fields() -> None:
    """as_dict exposes present/missing/extra/ok as plain values."""
    report = check_jobs(["lint", "test", "foo"])
    d = report.as_dict()
    assert d["present"] == list(report.present)
    assert d["missing"] == list(report.missing)
    assert d["extra"] == list(report.extra)
    assert d["ok"] == report.ok
    assert d["ok"] is False


def test_report_is_frozen() -> None:
    """CIJobReport is immutable — заморожен."""
    report = check_jobs(["lint"])
    assert isinstance(report, CIJobReport)
    try:
        report.ok = True  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("CIJobReport should be frozen")
