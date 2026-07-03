"""Tests for curation-vs-ingestion diff attribution (§16.10).

RU/EN: атрибуция / attribution, окно / window, доля / ratio.
"""

from __future__ import annotations

from kg_common.storage.diff_attribution import (
    AttributedDiff,
    attribute_changes,
    curation_ratio,
)

WINDOW = ("2026-07-01T00:00:00Z", "2026-07-03T23:59:59Z")


def test_in_window_event_lands_in_curation() -> None:
    changes = [{"target_id": "n1", "op": "update"}]
    events = [{"target_id": "n1", "created_at": "2026-07-02T12:00:00Z"}]
    result = attribute_changes(changes, events, WINDOW)
    assert [c["target_id"] for c in result.curation] == ["n1"]
    assert result.ingestion == []
    assert result.counts == {"curation": 1, "ingestion": 0, "total": 1}


def test_out_of_window_event_lands_in_ingestion() -> None:
    changes = [{"target_id": "n1"}]
    events = [{"target_id": "n1", "created_at": "2026-06-30T23:59:59Z"}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.curation == []
    assert [c["target_id"] for c in result.ingestion] == ["n1"]
    assert result.counts["ingestion"] == 1


def test_change_with_no_event_lands_in_ingestion() -> None:
    changes = [{"target_id": "n9"}]
    events: list[dict] = []
    result = attribute_changes(changes, events, WINDOW)
    assert result.curation == []
    assert result.counts == {"curation": 0, "ingestion": 1, "total": 1}


def test_boundary_event_at_window_start_is_inclusive() -> None:
    changes = [{"target_id": "n1"}]
    events = [{"target_id": "n1", "created_at": WINDOW[0]}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.counts["curation"] == 1
    assert result.ingestion == []


def test_boundary_event_at_window_end_is_inclusive() -> None:
    changes = [{"target_id": "n1"}]
    events = [{"target_id": "n1", "created_at": WINDOW[1]}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.counts["curation"] == 1


def test_total_equals_len_changes() -> None:
    changes = [{"target_id": f"n{i}"} for i in range(4)]
    events = [{"target_id": "n0", "created_at": "2026-07-02T00:00:00Z"}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.counts["total"] == len(changes)
    assert result.counts["curation"] + result.counts["ingestion"] == len(changes)


def test_curation_ratio_one_of_four() -> None:
    # n0 has an in-window event; n1,n2,n3 do not -> 1 curation of 4 total.
    changes = [{"target_id": f"n{i}"} for i in range(4)]
    events = [{"target_id": "n0", "created_at": "2026-07-02T00:00:00Z"}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.counts == {"curation": 1, "ingestion": 3, "total": 4}
    assert curation_ratio(result) == 0.25


def test_empty_changes_yield_zero_total_and_ratio() -> None:
    result = attribute_changes([], [], WINDOW)
    assert result.counts["total"] == 0
    assert curation_ratio(result) == 0.0


def test_as_dict_has_counts() -> None:
    result = attribute_changes([{"target_id": "n1"}], [], WINDOW)
    d = result.as_dict()
    assert "counts" in d
    assert d["counts"]["total"] == 1
    assert set(d) == {"curation", "ingestion", "counts"}


def test_event_for_different_target_does_not_attribute() -> None:
    changes = [{"target_id": "n1"}]
    events = [{"target_id": "other", "created_at": "2026-07-02T00:00:00Z"}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.counts["curation"] == 0
    assert result.counts["ingestion"] == 1


def test_event_with_none_created_at_is_ingestion() -> None:
    changes = [{"target_id": "n1"}]
    events = [{"target_id": "n1", "created_at": None}]
    result = attribute_changes(changes, events, WINDOW)
    assert result.counts["ingestion"] == 1


def test_result_is_frozen_attributed_diff() -> None:
    result = attribute_changes([], [], WINDOW)
    assert isinstance(result, AttributedDiff)
