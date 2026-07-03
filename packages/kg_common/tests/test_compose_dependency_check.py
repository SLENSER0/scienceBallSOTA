"""Tests for compose ``depends_on`` validation — тесты (§2.4)."""

from __future__ import annotations

from kg_common.compose_dependency_check import DependencyReport, check_dependencies


def test_healthy_dependency_is_ok() -> None:
    report = check_dependencies({"api": {"redis": "service_healthy"}, "redis": {}})
    assert report.ok is True
    assert report.weak_conditions == ()
    assert report.missing_targets == ()
    assert report.cycles == ()


def test_missing_target_fails_ok() -> None:
    report = check_dependencies({"api": {"db": "service_healthy"}})
    assert report.missing_targets == (("api", "db"),)
    assert report.ok is False


def test_weak_condition_surfaced_but_ok() -> None:
    report = check_dependencies({"api": {"redis": "service_started"}, "redis": {}})
    assert ("api", "redis") in report.weak_conditions
    # weak condition alone does not fail ok
    assert report.ok is True


def test_two_cycle_reported() -> None:
    report = check_dependencies({"a": {"b": "service_healthy"}, "b": {"a": "service_healthy"}})
    assert report.cycles  # non-empty
    assert report.ok is False
    # the single cycle canonicalises to ('a', 'b')
    assert report.cycles == (("a", "b"),)


def test_self_loop_is_a_cycle() -> None:
    report = check_dependencies({"a": {"a": "service_healthy"}})
    assert report.cycles == (("a",),)
    assert report.ok is False


def test_missing_targets_sorted() -> None:
    report = check_dependencies({"z": {"x": "service_healthy"}, "a": {"y": "service_healthy"}})
    assert report.missing_targets == (("a", "y"), ("z", "x"))


def test_as_dict_round_trips_all_four_fields() -> None:
    report = check_dependencies({"api": {"db": "service_started", "api": "service_healthy"}})
    d = report.as_dict()
    assert set(d) == {"cycles", "missing_targets", "weak_conditions", "ok"}
    assert d["cycles"] == [["api"]]
    assert d["missing_targets"] == [["api", "db"]]
    assert d["weak_conditions"] == [["api", "db"]]
    assert d["ok"] is False


def test_report_is_frozen() -> None:
    report = check_dependencies({"a": {}})
    try:
        report.ok = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("DependencyReport must be frozen")


def test_multiple_dependencies_missing_and_weak() -> None:
    report = check_dependencies(
        {
            "api": {"redis": "service_healthy", "worker": "service_started"},
            "redis": {},
            "worker": {"cache": "service_healthy"},
        }
    )
    # 'cache' is undeclared
    assert report.missing_targets == (("worker", "cache"),)
    assert report.weak_conditions == (("api", "worker"),)
    assert report.ok is False  # missing target fails ok


def test_dependency_report_constructible_directly() -> None:
    report = DependencyReport(cycles=(), missing_targets=(), weak_conditions=(), ok=True)
    assert report.as_dict()["ok"] is True
