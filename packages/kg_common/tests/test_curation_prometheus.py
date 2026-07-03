"""Tests for the §16.11 curation Prometheus metric family (hand-checkable).

Every instant is an explicit ISO-8601 string so ages are deterministic. ``NOW`` is
fixed; open-task ``created_at`` stamps are chosen so the backlog ages are exactly
``[1, 2, 100]`` hours for the p95 nearest-rank check.
"""

from __future__ import annotations

from kg_common.storage.curation_prometheus import (
    CurationMetrics,
    compute,
    render,
)

NOW = "2026-07-03T12:00:00"


def _open(created_at: str, task_type: str = "low_confidence") -> dict:
    return {"status": "open", "task_type": task_type, "created_at": created_at}


def _resolved(task_type: str = "contradiction") -> dict:
    return {"status": "resolved", "task_type": task_type}


def _auto(task_type: str = "contradiction") -> dict:
    return {"status": "auto_resolved", "task_type": task_type}


def test_tasks_open_counts_only_open() -> None:
    # (1) 3 open + 2 resolved -> tasks_open == 3
    tasks = [
        _open("2026-07-03T11:00:00"),
        _open("2026-07-03T10:00:00"),
        _open("2026-07-03T08:00:00"),
        _resolved(),
        _resolved(),
    ]
    metrics = compute(tasks, now_iso=NOW)
    assert metrics.tasks_open == 3


def test_resolved_total_keyed_by_task_type() -> None:
    # (2) both resolved are contradictions -> resolved_total['contradiction'] == 2
    tasks = [_resolved("contradiction"), _resolved("contradiction")]
    metrics = compute(tasks, now_iso=NOW)
    assert metrics.resolved_total["contradiction"] == 2


def test_auto_resolved_ratio_half() -> None:
    # (3) 1 auto_resolved + 1 resolved -> ratio == 0.5
    tasks = [_auto(), _resolved()]
    metrics = compute(tasks, now_iso=NOW)
    assert metrics.auto_resolved_ratio == 0.5


def test_p95_nearest_rank_over_open_ages() -> None:
    # (4) open ages [1, 2, 100]h -> p95 nearest-rank == 100.0
    tasks = [
        _open("2026-07-03T11:00:00"),  # 1h before NOW
        _open("2026-07-03T10:00:00"),  # 2h before NOW
        _open("2026-06-29T08:00:00"),  # 100h before NOW
    ]
    metrics = compute(tasks, now_iso=NOW)
    assert metrics.review_backlog_age_p95 == 100.0


def test_protected_count_surfaced() -> None:
    # (5) protected_count 7 -> verified_fields_protected_total == 7
    metrics = compute([], now_iso=NOW, protected_count=7)
    assert metrics.verified_fields_protected_total == 7


def test_render_contains_open_series() -> None:
    # (6) render() output contains 'curation_tasks_open 3'
    tasks = [
        _open("2026-07-03T11:00:00"),
        _open("2026-07-03T10:00:00"),
        _open("2026-07-03T08:00:00"),
    ]
    text = render(compute(tasks, now_iso=NOW))
    assert "curation_tasks_open 3" in text


def test_no_tasks_zero_ratio_no_division() -> None:
    # (7) no tasks -> auto_resolved_ratio == 0.0 (no ZeroDivisionError)
    metrics = compute([], now_iso=NOW)
    assert metrics.auto_resolved_ratio == 0.0
    assert metrics.tasks_open == 0
    assert metrics.review_backlog_age_p95 == 0.0
    assert metrics.resolved_total == {}


def test_as_dict_roundtrip_and_frozen() -> None:
    metrics = compute([_auto("contradiction")], now_iso=NOW, protected_count=2)
    data = metrics.as_dict()
    assert data["auto_resolved_ratio"] == 1.0
    assert data["resolved_total"] == {"contradiction": 1}
    assert data["verified_fields_protected_total"] == 2
    # frozen: mutating the returned dict does not touch the instance
    data["resolved_total"]["contradiction"] = 999
    assert metrics.resolved_total["contradiction"] == 1


def test_render_full_series_present() -> None:
    tasks = [_auto("contradiction"), _resolved("stale")]
    text = render(compute(tasks, now_iso=NOW, protected_count=4))
    assert 'curation_tasks_resolved_total{task_type="contradiction"} 1' in text
    assert 'curation_tasks_resolved_total{task_type="stale"} 1' in text
    assert "verified_fields_protected_total 4" in text
    assert "auto_resolved_ratio 0.5" in text
    assert "review_backlog_age_p95 0" in text


def test_auto_resolved_via_flag() -> None:
    # a status="resolved" row with an auto_resolved flag counts as auto
    tasks = [{"status": "resolved", "task_type": "dup", "auto_resolved": True}]
    metrics = compute(tasks, now_iso=NOW)
    assert metrics.auto_resolved_ratio == 1.0
    assert metrics.resolved_total["dup"] == 1


def test_returns_curation_metrics_type() -> None:
    assert isinstance(compute([], now_iso=NOW), CurationMetrics)
