"""Gap trends across scan runs — hand-checked opened / closed / net change (§15.11).

Pure-Python: every snapshot is a plain ``{run_id, created_at, gap_ids}`` mapping, so
each assertion pins concrete expected numbers that are trivial to verify by eye.
"""

from __future__ import annotations

import pytest

from kg_retrievers.gap_trends import (
    DIR_IMPROVING,
    DIR_STABLE,
    DIR_WORSENING,
    UNKNOWN_TYPE,
    GapTrend,
    compute_trends,
    trend_direction,
)


def _snap(run_id: str, gap_ids: list, created_at: str = "2026-07-03T00:00:00Z") -> dict:
    return {"run_id": run_id, "created_at": created_at, "gap_ids": gap_ids}


def test_two_snapshots_opened_and_closed_counted() -> None:
    # s0 -> s1: g3,g4 appear (opened=2); g1 disappears (closed=1); net = 2-1 = 1.
    trend = compute_trends([_snap("r0", ["g1", "g2"]), _snap("r1", ["g2", "g3", "g4"])])
    assert trend.opened == 2
    assert trend.closed == 1
    assert trend.net_change == 1
    # first point has no predecessor -> zeros; second carries the transition counts
    assert trend.points[0]["opened"] == 0
    assert trend.points[0]["closed"] == 0
    assert trend.points[0]["gaps"] == 2
    assert trend.points[1]["opened"] == 2
    assert trend.points[1]["closed"] == 1
    assert trend.points[1]["net_change"] == 1
    assert trend.points[1]["gaps"] == 3
    assert trend.points[1]["run_id"] == "r1"


def test_net_change_per_step() -> None:
    # s0=[g1,g2,g3] -> s1=[g1,g2] (close g3, net -1) -> s2=[g1,g2,g4,g5] (open 2, net +2).
    snaps = [
        _snap("r0", ["g1", "g2", "g3"]),
        _snap("r1", ["g1", "g2"]),
        _snap("r2", ["g1", "g2", "g4", "g5"]),
    ]
    trend = compute_trends(snaps)
    assert [p["net_change"] for p in trend.points] == [0, -1, 2]
    assert [p["opened"] for p in trend.points] == [0, 0, 2]
    assert [p["closed"] for p in trend.points] == [0, 1, 0]
    # totals: opened 0+0+2=2, closed 0+1+0=1, net = |last|4 - |first|3 = 1
    assert trend.opened == 2
    assert trend.closed == 1
    assert trend.net_change == 1


def test_fully_closed_gap_counted_once() -> None:
    # g1 present then gone for good: closed exactly once, never re-counted.
    snaps = [_snap("r0", ["g1"]), _snap("r1", []), _snap("r2", [])]
    trend = compute_trends(snaps)
    assert trend.closed == 1
    assert trend.opened == 0
    assert trend.net_change == -1
    assert [p["closed"] for p in trend.points] == [0, 1, 0]


def test_stable_when_identical() -> None:
    # Two identical snapshots: nothing opened or closed -> stable.
    trend = compute_trends([_snap("r0", ["g1", "g2"]), _snap("r1", ["g1", "g2"])])
    assert trend.opened == 0
    assert trend.closed == 0
    assert trend.net_change == 0
    assert trend_direction(trend) == DIR_STABLE


def test_improving_when_gaps_shrink() -> None:
    # Backlog drops from 3 to 1: net_change -2 -> improving.
    trend = compute_trends([_snap("r0", ["g1", "g2", "g3"]), _snap("r1", ["g1"])])
    assert trend.net_change == -2
    assert trend_direction(trend) == DIR_IMPROVING


def test_worsening_when_gaps_grow() -> None:
    # Backlog grows from 1 to 3: net_change +2 -> worsening.
    trend = compute_trends([_snap("r0", ["g1"]), _snap("r1", ["g1", "g2", "g3"])])
    assert trend.net_change == 2
    assert trend_direction(trend) == DIR_WORSENING


def test_single_snapshot_yields_zeros() -> None:
    # One snapshot has no predecessor: all deltas zero, one point, empty by_type.
    trend = compute_trends([_snap("r0", ["g1", "g2"])])
    assert trend.opened == 0
    assert trend.closed == 0
    assert trend.net_change == 0
    assert trend.by_type_delta == {}
    assert len(trend.points) == 1
    assert trend.points[0]["gaps"] == 2
    assert trend_direction(trend) == DIR_STABLE


def test_empty_series_is_all_zero() -> None:
    trend = compute_trends([])
    assert trend.points == []
    assert trend.opened == 0
    assert trend.closed == 0
    assert trend.net_change == 0
    assert trend.by_type_delta == {}
    assert trend_direction(trend) == DIR_STABLE


def test_by_type_delta_from_typed_entries() -> None:
    # Typed entries: g2 (missing_unit) and g3 (orphan_entity) open -> +1 each.
    s0 = _snap("r0", [{"id": "g1", "gap_type": "missing_unit"}])
    s1 = _snap(
        "r1",
        [
            {"id": "g1", "gap_type": "missing_unit"},
            {"id": "g2", "gap_type": "missing_unit"},
            {"id": "g3", "gap_type": "orphan_entity"},
        ],
    )
    trend = compute_trends([s0, s1])
    assert trend.by_type_delta == {"missing_unit": 1, "orphan_entity": 1}
    # by_type_delta always sums back to net_change
    assert sum(trend.by_type_delta.values()) == trend.net_change == 2


def test_by_type_delta_counts_closures_negative() -> None:
    # g2 (orphan_entity) closes -> its delta is -1; untouched types are dropped.
    s0 = _snap(
        "r0",
        [
            {"id": "g1", "gap_type": "missing_unit"},
            {"id": "g2", "gap_type": "orphan_entity"},
        ],
    )
    s1 = _snap("r1", [{"id": "g1", "gap_type": "missing_unit"}])
    trend = compute_trends([s0, s1])
    assert trend.by_type_delta == {"orphan_entity": -1}
    assert trend.net_change == -1


def test_untyped_entries_bucket_under_unknown() -> None:
    # Bare-string ids carry no type -> they land in the RU fallback bucket.
    trend = compute_trends([_snap("r0", ["g1"]), _snap("r1", ["g1", "g2"])])
    assert trend.by_type_delta == {UNKNOWN_TYPE: 1}


def test_duplicate_ids_within_snapshot_deduped() -> None:
    # A repeated id inside one snapshot counts once; no phantom open/close events.
    trend = compute_trends([_snap("r0", ["g1", "g1", "g2"]), _snap("r1", ["g1", "g2"])])
    assert trend.points[0]["gaps"] == 2
    assert trend.opened == 0
    assert trend.closed == 0


def test_as_dict_round_trips() -> None:
    trend = compute_trends([_snap("r0", ["g1", "g2"]), _snap("r1", ["g2", "g3"])])
    d = trend.as_dict()
    assert d["opened"] == 1
    assert d["closed"] == 1
    assert d["net_change"] == 0
    assert d["by_type_delta"] == {}
    assert len(d["points"]) == 2
    assert d["points"][1] == {
        "run_id": "r1",
        "created_at": "2026-07-03T00:00:00Z",
        "gaps": 2,
        "opened": 1,
        "closed": 1,
        "net_change": 0,
    }
    # as_dict returns copies: mutating them leaves the frozen trend intact
    d["points"][0]["gaps"] = 999
    assert trend.points[0]["gaps"] == 2


def test_gap_trend_is_frozen() -> None:
    trend = compute_trends([_snap("r0", ["g1"])])
    assert isinstance(trend, GapTrend)
    with pytest.raises(AttributeError):
        trend.opened = 5  # type: ignore[misc]
