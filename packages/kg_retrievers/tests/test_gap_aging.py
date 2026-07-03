"""Tests for gap aging & SLA-breach classification (§15.9/§15.2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from kg_retrievers.gap_aging import (
    DEFAULT_SLA_DAYS,
    SLA_DAYS,
    GapAge,
    age_of,
    aging_report,
)

# Fixed reference clock so every age is exactly hand-checkable.
NOW = datetime(2026, 7, 3, 12, 0, 0)


def _gap(gid, severity, status, days_ago):
    detected = (NOW - timedelta(days=days_ago)).isoformat()
    return {"id": gid, "severity": severity, "status": status, "detected_at": detected}


def test_critical_breach() -> None:
    # (1) critical, 5 days old, SLA 3 → breached, overdue 2.
    res = age_of(_gap("g1", "critical", "open", 5), NOW)
    assert res.age_days == 5.0
    assert res.sla_days == 3
    assert res.breached is True
    assert res.overdue_days == 2.0


def test_low_within_sla() -> None:
    # (2) low, 10 days old, SLA 90 → not breached, no overdue.
    res = age_of(_gap("g2", "low", "open", 10), NOW)
    assert res.sla_days == SLA_DAYS["low"] == 90
    assert res.breached is False
    assert res.overdue_days == 0.0


def test_unknown_severity_falls_back() -> None:
    # (3) unknown severity → default SLA of 30.
    res = age_of(_gap("g3", "spicy", "open", 1), NOW)
    assert res.sla_days == DEFAULT_SLA_DAYS == 30


def test_resolved_never_breaches() -> None:
    # (4) resolved gap, ancient, still breached False, overdue 0.
    res = age_of(_gap("g4", "critical", "resolved", 999), NOW)
    assert res.age_days == 999.0
    assert res.breached is False
    assert res.overdue_days == 0.0


def test_as_dict_round_trips() -> None:
    # (5) as_dict exposes all six keys and reconstructs the dataclass.
    res = age_of(_gap("g5", "high", "open", 8), NOW)
    d = res.as_dict()
    assert set(d) == {
        "gap_id",
        "severity",
        "age_days",
        "sla_days",
        "breached",
        "overdue_days",
    }
    assert GapAge(**d) == res


def test_report_orders_by_overdue() -> None:
    # (6) critical breach sorts ahead of a non-breached low gap.
    gaps = [
        _gap("low", "low", "open", 10),
        _gap("crit", "critical", "open", 5),
    ]
    report = aging_report(gaps, NOW)
    assert [a.gap_id for a in report] == ["crit", "low"]
    assert report[0].overdue_days == 2.0
    assert report[1].overdue_days == 0.0


def test_empty_report() -> None:
    # (7) empty input → empty output.
    assert aging_report([], NOW) == []


def test_malformed_detected_at() -> None:
    # (8) missing / malformed detected_at → age 0, not breached.
    missing = {"id": "g8", "severity": "critical", "status": "open"}
    res = age_of(missing, NOW)
    assert res.age_days == 0.0
    assert res.breached is False
    assert res.overdue_days == 0.0

    bad = {"id": "g9", "severity": "critical", "status": "open", "detected_at": "not-a-date"}
    res2 = age_of(bad, NOW)
    assert res2.age_days == 0.0
    assert res2.breached is False
