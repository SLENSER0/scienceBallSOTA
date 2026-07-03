"""Tests for pipeline stage-trace assertions (§23.1)."""

from __future__ import annotations

from kg_eval.pipeline_trace_assertions import (
    StageEvent,
    TraceAssertion,
    check_trace,
)

ORDER = ("ingest", "extract", "index", "retrieve", "answer")


def _trace() -> list[StageEvent]:
    """A well-formed in-order trace, one event per expected stage."""
    return [
        StageEvent("ingest", 0.0, 10.0),
        StageEvent("extract", 10.0, 30.0),
        StageEvent("index", 30.0, 45.0),
        StageEvent("retrieve", 45.0, 60.0),
        StageEvent("answer", 60.0, 100.0),
    ]


def test_all_stages_in_order_no_budget_ok() -> None:
    res = check_trace(_trace(), expected_order=ORDER)
    assert res.ok is True
    assert res.missing_stages == ()
    assert res.out_of_order == ()
    assert res.over_budget == ()


def test_missing_stage_listed_and_not_ok() -> None:
    events = [e for e in _trace() if e.stage != "index"]
    res = check_trace(events, expected_order=ORDER)
    assert res.ok is False
    assert res.missing_stages == ("index",)
    assert res.out_of_order == ()


def test_swapped_adjacent_stages_out_of_order() -> None:
    events = _trace()
    # Swap extract and index so index's first occurrence precedes extract's.
    events[1], events[2] = events[2], events[1]
    res = check_trace(events, expected_order=ORDER)
    assert res.ok is False
    # "index" first-occurs before "extract" though expected after -> flagged.
    assert res.out_of_order != ()
    assert "index" in res.out_of_order


def test_over_budget_stage_flagged() -> None:
    events = _trace()  # extract lasts 20ms
    res = check_trace(events, expected_order=ORDER, budgets_ms={"extract": 15.0})
    assert res.ok is False
    assert res.over_budget == ("extract",)
    assert res.missing_stages == ()
    assert res.out_of_order == ()


def test_within_budget_ok() -> None:
    res = check_trace(_trace(), expected_order=ORDER, budgets_ms={"extract": 25.0})
    assert res.ok is True
    assert res.over_budget == ()


def test_total_ms_is_span_first_start_to_last_end() -> None:
    res = check_trace(_trace(), expected_order=ORDER)
    # min start = 0.0, max end = 100.0
    assert res.total_ms == 100.0


def test_total_ms_ignores_event_gaps_and_overlaps() -> None:
    events = [
        StageEvent("ingest", 5.0, 8.0),
        StageEvent("extract", 20.0, 55.0),
    ]
    res = check_trace(events, expected_order=("ingest", "extract"))
    assert res.total_ms == 50.0  # 55 - 5


def test_duration_ms_property() -> None:
    ev = StageEvent("extract", 10.0, 30.0)
    assert ev.duration_ms == 20.0
    assert ev.duration_ms == ev.end_ms - ev.start_ms


def test_empty_events_all_missing() -> None:
    res = check_trace([], expected_order=ORDER)
    assert res.ok is False
    assert res.missing_stages == ORDER
    assert res.total_ms == 0.0


def test_as_dict_ok_is_bool() -> None:
    res = check_trace(_trace(), expected_order=ORDER)
    d = res.as_dict()
    assert isinstance(d["ok"], bool)
    assert d["ok"] is True
    assert d["missing_stages"] == []
    assert d["total_ms"] == 100.0


def test_stage_event_as_dict() -> None:
    ev = StageEvent("index", 30.0, 45.0)
    d = ev.as_dict()
    assert d == {
        "stage": "index",
        "start_ms": 30.0,
        "end_ms": 45.0,
        "duration_ms": 15.0,
    }


def test_frozen_dataclasses() -> None:
    res = TraceAssertion(True, (), (), (), 1.0)
    for obj, attr, val in ((res, "ok", False), (StageEvent("a", 0, 1), "stage", "b")):
        try:
            setattr(obj, attr, val)
        except AttributeError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected frozen dataclass")


def test_repeated_stage_uses_first_occurrence_for_order() -> None:
    events = [
        StageEvent("ingest", 0.0, 5.0),
        StageEvent("extract", 5.0, 10.0),
        StageEvent("ingest", 10.0, 12.0),  # retry, later occurrence
        StageEvent("index", 12.0, 15.0),
    ]
    res = check_trace(events, expected_order=("ingest", "extract", "index"))
    assert res.out_of_order == ()
    assert res.ok is True


def test_over_budget_only_flags_stage_once() -> None:
    events = [
        StageEvent("extract", 0.0, 40.0),
        StageEvent("extract", 40.0, 90.0),
    ]
    res = check_trace(events, expected_order=("extract",), budgets_ms={"extract": 10.0})
    assert res.over_budget == ("extract",)
