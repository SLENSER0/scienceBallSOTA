"""Tests for asset-check outcome modelling — тесты сводки проверок (§9.4)."""

from __future__ import annotations

import pytest

from kg_common.asset_check_result import (
    VALID_SEVERITIES,
    CheckResult,
    aggregate,
    blocking,
)


def test_valid_error_check_builds() -> None:
    """A valid ERROR check constructs — валидная ERROR-проверка строится."""
    r = CheckResult(name="neo4j", passed=False, severity="ERROR")
    assert r.name == "neo4j"
    assert r.passed is False
    assert r.severity == "ERROR"
    assert dict(r.metadata) == {}
    assert "ERROR" in VALID_SEVERITIES


def test_info_severity_raises() -> None:
    """Severity 'INFO' is rejected — недопустимый уровень поднимает ошибку."""
    with pytest.raises(ValueError):
        CheckResult(name="x", passed=True, severity="INFO")


def test_empty_name_raises() -> None:
    """Empty (and blank) name is rejected — пустое имя поднимает ошибку."""
    with pytest.raises(ValueError):
        CheckResult(name="", passed=True, severity="WARN")
    with pytest.raises(ValueError):
        CheckResult(name="   ", passed=True, severity="WARN")


def test_blocking_true_for_failed_error() -> None:
    """A failed ERROR blocks — упавшая ERROR-проверка блокирует."""
    assert blocking(CheckResult("neo4j", False, "ERROR")) is True


def test_blocking_false_for_failed_warn() -> None:
    """A failed WARN does not block — упавшая WARN-проверка не блокирует."""
    assert blocking(CheckResult("x", False, "WARN")) is False


def test_blocking_false_for_passing_error() -> None:
    """A passing ERROR does not block — пройденная ERROR не блокирует."""
    assert blocking(CheckResult("qdrant", True, "ERROR")) is False


def test_aggregate_empty_is_ok() -> None:
    """Empty aggregate is vacuously ok — пустая сводка ok, total==0."""
    agg = aggregate([])
    assert agg["ok"] is True
    assert agg["total"] == 0
    assert agg["passed"] == 0
    assert agg["failed"] == 0
    assert agg["blocking"] == 0
    assert agg["worst_severity"] is None


def test_aggregate_pass_and_warn_failure_ok() -> None:
    """A pass + failed WARN stays ok with failed==1 — WARN не роняет ok."""
    ok_check = CheckResult("bm25", True, "WARN")
    warn_fail = CheckResult("cache", False, "WARN")
    agg = aggregate([ok_check, warn_fail])
    assert agg["ok"] is True
    assert agg["total"] == 2
    assert agg["passed"] == 1
    assert agg["failed"] == 1
    assert agg["blocking"] == 0
    assert agg["worst_severity"] == "WARN"


def test_aggregate_error_failure_blocks() -> None:
    """A failed ERROR blocks the verdict — ERROR роняет ok, worst==ERROR."""
    error_fail = CheckResult("neo4j", False, "ERROR")
    agg = aggregate([error_fail])
    assert agg["blocking"] == 1
    assert agg["worst_severity"] == "ERROR"
    assert agg["ok"] is False
    assert agg["failed"] == 1


def test_worst_severity_error_dominates_warn() -> None:
    """ERROR outranks WARN in worst_severity — ERROR доминирует над WARN."""
    checks = [
        CheckResult("a", True, "WARN"),
        CheckResult("b", False, "ERROR"),
        CheckResult("c", True, "WARN"),
    ]
    assert aggregate(checks)["worst_severity"] == "ERROR"


def test_as_dict_roundtrip() -> None:
    """as_dict exposes severity, metadata and blocking — сериализация."""
    r = CheckResult("cache", False, "WARN", {"latency_ms": 12})
    d = r.as_dict()
    assert d["severity"] == "WARN"
    assert d["name"] == "cache"
    assert d["passed"] is False
    assert d["metadata"] == {"latency_ms": 12}
    assert d["blocking"] is False
