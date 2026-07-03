"""Tests for team & lab activity aggregation (§24.15)."""

from __future__ import annotations

from kg_retrievers.team_activity import ActivitySummary, summarize_activity


def _event(entity_id: str, kind: str, activity_type: str, date: str) -> dict:
    return {
        "entity_id": entity_id,
        "entity_kind": kind,
        "activity_type": activity_type,
        "date": date,
    }


def test_three_events_two_types_one_lab_counts_and_total() -> None:
    events = [
        _event("lab-1", "lab", "publication", "2026-02-01"),
        _event("lab-1", "lab", "publication", "2026-03-01"),
        _event("lab-1", "lab", "experiment", "2026-01-15"),
    ]
    (summary,) = summarize_activity(events)
    assert summary.counts == {"publication": 2, "experiment": 1}
    assert summary.total == 3
    assert summary.entity_id == "lab-1"
    assert summary.entity_kind == "lab"


def test_latest_date_is_newest_string() -> None:
    events = [
        _event("lab-1", "lab", "report", "2026-02-01"),
        _event("lab-1", "lab", "report", "2026-05-20"),
        _event("lab-1", "lab", "report", "2026-03-10"),
    ]
    (summary,) = summarize_activity(events)
    assert summary.latest_date == "2026-05-20"


def test_since_drops_old_event_from_total_and_counts() -> None:
    events = [
        _event("lab-1", "lab", "publication", "2025-12-31"),
        _event("lab-1", "lab", "publication", "2026-02-01"),
        _event("lab-1", "lab", "experiment", "2026-03-01"),
    ]
    (summary,) = summarize_activity(events, since="2026-01-01")
    assert summary.total == 2
    assert summary.counts == {"publication": 1, "experiment": 1}
    assert summary.latest_date == "2026-03-01"


def test_two_entities_sorted_by_total_desc() -> None:
    events = [
        _event("expert-a", "expert", "curation", "2026-01-01"),
        _event("lab-b", "lab", "publication", "2026-01-02"),
        _event("lab-b", "lab", "publication", "2026-01-03"),
        _event("lab-b", "lab", "report", "2026-01-04"),
    ]
    summaries = summarize_activity(events)
    assert [s.entity_id for s in summaries] == ["lab-b", "expert-a"]
    assert [s.total for s in summaries] == [3, 1]


def test_ties_broken_by_entity_id_asc() -> None:
    events = [
        _event("zeta", "lab", "publication", "2026-01-01"),
        _event("alpha", "lab", "publication", "2026-01-01"),
    ]
    summaries = summarize_activity(events)
    assert [s.entity_id for s in summaries] == ["alpha", "zeta"]


def test_unrecognized_activity_type_tallied_under_own_key() -> None:
    events = [
        _event("lab-1", "lab", "publication", "2026-01-01"),
        _event("lab-1", "lab", "mystery_ritual", "2026-01-02"),
    ]
    (summary,) = summarize_activity(events)
    assert summary.counts == {"publication": 1, "mystery_ritual": 1}
    assert summary.total == 2


def test_empty_events_returns_empty_list() -> None:
    assert summarize_activity([]) == []


def test_as_dict_counts_equals_tally() -> None:
    events = [
        _event("lab-1", "lab", "publication", "2026-01-01"),
        _event("lab-1", "lab", "publication", "2026-01-02"),
        _event("lab-1", "lab", "curation", "2026-01-03"),
    ]
    (summary,) = summarize_activity(events)
    d = summary.as_dict()
    assert d["counts"] == {"publication": 2, "curation": 1}
    assert d["total"] == 3
    assert d["latest_date"] == "2026-01-03"
    assert d["entity_id"] == "lab-1"
    assert d["entity_kind"] == "lab"


def test_single_event_entity_total_one() -> None:
    events = [_event("expert-x", "expert", "report", "2026-04-04")]
    (summary,) = summarize_activity(events)
    assert summary.total == 1
    assert summary.counts == {"report": 1}
    assert summary.latest_date == "2026-04-04"


def test_summary_is_frozen() -> None:
    summary = ActivitySummary(
        entity_id="lab-1",
        entity_kind="lab",
        counts={"report": 1},
        total=1,
        latest_date="2026-01-01",
    )
    try:
        summary.total = 2  # type: ignore[misc]
    except Exception as exc:  # pragma: no cover - attribute error path
        assert "cannot assign" in str(exc) or "frozen" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("ActivitySummary should be frozen")
