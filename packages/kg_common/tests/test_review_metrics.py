"""Review-queue throughput + aging metrics (§16.11) — hand-checked pure-function tests."""

from __future__ import annotations

from kg_common.storage.review_metrics import (
    TREND_IMPROVING,
    TREND_STABLE,
    TREND_WORSENING,
    QueueMetrics,
    backlog_trend,
    queue_metrics,
    throughput,
)

_NOW = "2026-01-02T00:00:00"  # общий "сейчас" для возраста (24h после суток начала)


def test_counts_by_status() -> None:
    tasks = [
        {"status": "open", "kind": "low_confidence", "created_at": "2026-01-01T00:00:00"},
        {"status": "open", "kind": "low_confidence", "created_at": "2026-01-01T12:00:00"},
        {"status": "in_review", "kind": "conflicting", "created_at": "2026-01-01T00:00:00"},
        {"status": "resolved", "kind": "conflicting", "created_at": "2026-01-01T00:00:00"},
        {"status": "resolved", "kind": "schema_change", "created_at": "2026-01-01T00:00:00"},
    ]
    m = queue_metrics(tasks, now=_NOW)
    assert m.total == 5
    assert m.open == 2
    assert m.in_review == 1
    assert m.resolved == 2
    assert m.overdue == 0  # no row carries an sla_hours, so nothing can be overdue


def test_overdue_counts_past_sla_open_task() -> None:
    tasks = [
        # open, 24h old vs a 12h SLA -> past SLA -> overdue
        {"status": "open", "kind": "k", "created_at": "2026-01-01T00:00:00", "sla_hours": 12},
        # open, 6h old vs a 12h SLA -> still within SLA
        {"status": "open", "kind": "k", "created_at": "2026-01-01T18:00:00", "sla_hours": 12},
        # open, 24h old but no SLA declared -> cannot be overdue
        {"status": "open", "kind": "k", "created_at": "2026-01-01T00:00:00"},
        # in_review, 24h old vs 1h SLA -> not open, not part of aging
        {"status": "in_review", "kind": "k", "created_at": "2026-01-01T00:00:00", "sla_hours": 1},
        # resolved, 24h old vs 1h SLA -> left the queue, not overdue
        {"status": "resolved", "kind": "k", "created_at": "2026-01-01T00:00:00", "sla_hours": 1},
    ]
    m = queue_metrics(tasks, now=_NOW)
    assert m.open == 3
    assert m.overdue == 1  # only the first open task is past its SLA


def test_avg_and_oldest_age_from_now() -> None:
    tasks = [
        {"status": "open", "kind": "k", "created_at": "2026-01-01T00:00:00"},  # 24h
        {"status": "open", "kind": "k", "created_at": "2026-01-01T18:00:00"},  # 6h
        # in_review / resolved rows must NOT affect the open-backlog aging
        {"status": "in_review", "kind": "k", "created_at": "2025-01-01T00:00:00"},
        {"status": "resolved", "kind": "k", "created_at": "2025-01-01T00:00:00"},
    ]
    m = queue_metrics(tasks, now=_NOW)
    assert m.avg_age_hours == 15.0  # mean of [24.0, 6.0]
    assert m.oldest_age_hours == 24.0  # the 24h-old open task


def test_by_kind_buckets_over_all_rows() -> None:
    tasks = [
        {"status": "open", "kind": "low_confidence", "created_at": "2026-01-01T00:00:00"},
        {"status": "resolved", "kind": "low_confidence", "created_at": "2026-01-01T00:00:00"},
        {"status": "in_review", "kind": "conflicting", "created_at": "2026-01-01T00:00:00"},
        {"status": "open", "kind": "schema_change", "created_at": "2026-01-01T00:00:00"},
    ]
    m = queue_metrics(tasks, now=_NOW)
    # histogram spans every status, sorted by kind
    assert m.by_kind == {"conflicting": 1, "low_confidence": 2, "schema_change": 1}


def test_throughput_counts_resolved_in_window() -> None:
    since = "2026-01-01T00:00:00"
    tasks = [
        {"status": "resolved", "kind": "k", "resolved_at": "2026-01-01T05:00:00"},  # inside
        {"status": "resolved", "kind": "k", "resolved_at": "2026-01-01T23:00:00"},  # inside
        {"status": "resolved", "kind": "k", "resolved_at": "2026-01-01T00:00:00"},  # == since
        {"status": "resolved", "kind": "k", "resolved_at": "2026-01-02T00:00:00"},  # == now
        {"status": "resolved", "kind": "k", "resolved_at": "2025-12-31T23:00:00"},  # before
        {"status": "resolved", "kind": "k", "resolved_at": "2026-01-02T05:00:00"},  # after
        {"status": "resolved", "kind": "k"},  # resolved but no resolved_at -> skip
        {"status": "open", "kind": "k", "resolved_at": "2026-01-01T05:00:00"},  # not resolved
    ]
    # both window bounds are inclusive: the four in-window resolutions count
    assert throughput(tasks, since=since, now=_NOW) == 4


def test_backlog_trend_improving_worsening_stable() -> None:
    assert backlog_trend([10, 7, 3]) == TREND_IMPROVING  # open shrinks -> improving
    assert backlog_trend([10, 7, 3]) == "improving"
    assert backlog_trend([3, 7, 10]) == TREND_WORSENING  # open grows -> worsening
    assert backlog_trend([5, 5, 5]) == TREND_STABLE  # flat -> stable
    assert backlog_trend([5, 9, 5]) == TREND_STABLE  # equal endpoints -> stable


def test_backlog_trend_accepts_metrics_mappings_and_ints() -> None:
    hi = QueueMetrics(5, 5, 0, 0, 0, 0.0, 0.0, {})
    lo = QueueMetrics(5, 1, 0, 4, 0, 0.0, 0.0, {})
    assert backlog_trend([hi, lo]) == TREND_IMPROVING  # QueueMetrics snapshots
    assert backlog_trend([hi.as_dict(), lo.as_dict()]) == TREND_IMPROVING  # mapping snapshots
    assert backlog_trend([{"open": 3}, {"open": 8}]) == TREND_WORSENING  # bare mappings


def test_empty_queue_is_all_zeros() -> None:
    m = queue_metrics([], now="2026-01-01T00:00:00")
    assert m.total == 0
    assert m.open == 0
    assert m.in_review == 0
    assert m.resolved == 0
    assert m.overdue == 0
    assert m.avg_age_hours == 0.0
    assert m.oldest_age_hours == 0.0
    assert m.by_kind == {}
    assert throughput([], since="2026-01-01T00:00:00", now=_NOW) == 0
    assert backlog_trend([]) == TREND_STABLE  # no data -> stable
    assert backlog_trend([{"open": 4}]) == TREND_STABLE  # single snapshot -> stable


def test_queue_metrics_as_dict() -> None:
    tasks = [
        {
            "status": "open",
            "kind": "low_confidence",
            "created_at": "2026-01-01T00:00:00",
            "sla_hours": 12,
        },
        {
            "status": "resolved",
            "kind": "conflicting",
            "created_at": "2026-01-01T00:00:00",
            "resolved_at": "2026-01-01T06:00:00",
        },
    ]
    m = queue_metrics(tasks, now=_NOW)
    assert m.as_dict() == {
        "total": 2,
        "open": 1,
        "in_review": 0,
        "resolved": 1,
        "overdue": 1,  # the open task is 24h old vs a 12h SLA
        "avg_age_hours": 24.0,
        "oldest_age_hours": 24.0,
        "by_kind": {"conflicting": 1, "low_confidence": 1},
    }
    # as_dict returns a fresh copy: mutating it never touches the frozen instance
    dumped = m.as_dict()
    dumped["by_kind"]["low_confidence"] = 999
    assert m.by_kind == {"conflicting": 1, "low_confidence": 1}
