"""Tests for §17.7 tool-call timeline (agent transparency / прозрачность агента).

Hand-checkable projection tests over captured trace dicts. Timestamps use whole
milliseconds so every expected number is verifiable by eye (offsets, span, counts).
"""

from __future__ import annotations

from agent_service.tool_timeline import (
    STATUS_ICONS,
    STEP_LABELS,
    ToolTimeline,
    build_tool_timeline,
)


def _entry(
    name: str,
    started_at: int,
    finished_at: int,
    status: str = "ok",
) -> dict[str, object]:
    """A captured trace dict (spec shape: name/startedAt/finishedAt/durationMs/...)."""
    return {
        "name": name,
        "args": {},
        "status": status,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "durationMs": finished_at - started_at,
        "summary": f"{name} ran",
        "dataRef": None,
    }


def test_step_labels_cover_the_five_ui_stages() -> None:
    """STEP_LABELS maps exactly the five §5.2.2 stages to their UI labels."""
    assert STEP_LABELS == {
        "resolve": "resolved entities",
        "graph_query": "graph query",
        "vector_search": "vector search",
        "evidence_check": "evidence check",
        "gap_scan": "gap scan",
    }


def test_status_icons_map_statuses_to_icon_keys() -> None:
    """STATUS_ICONS maps ok/error/running/'' to done/error/running/pending."""
    assert STATUS_ICONS == {
        "ok": "done",
        "error": "error",
        "running": "running",
        "": "pending",
    }


def test_empty_trace_is_a_zero_timeline() -> None:
    """An empty trace -> zero duration, no steps, no status counts."""
    timeline = build_tool_timeline([])
    assert isinstance(timeline, ToolTimeline)
    assert timeline.total_duration_ms == 0
    assert timeline.steps == ()
    assert timeline.status_counts == {}
    assert timeline.as_dict() == {"steps": [], "totalDurationMs": 0, "statusCounts": {}}


def test_two_entry_trace_offsets_labels_icons_and_total() -> None:
    """resolve (40ms) then graph_query (120ms) -> span 160ms, offsets and labels."""
    # resolve: [0, 40] = 40ms; graph_query: [40, 160] = 120ms (non-overlapping / без наложения).
    trace = [
        _entry("resolve", 0, 40),
        _entry("graph_query", 40, 160),
    ]
    timeline = build_tool_timeline(trace)

    assert timeline.total_duration_ms == 160  # 40 + 120 == max(finishedAt) - min(startedAt)
    assert timeline.steps[0]["offsetMs"] == 0
    assert timeline.steps[1]["offsetMs"] == 40  # startedAt diff: 40 - 0
    assert timeline.steps[0]["label"] == "resolved entities"
    assert timeline.steps[1]["label"] == "graph query"
    assert timeline.steps[0]["iconKey"] == "done"
    assert timeline.steps[1]["iconKey"] == "done"
    assert timeline.status_counts == {"ok": 2}


def test_error_entry_gets_error_icon_and_is_counted() -> None:
    """A status='error' entry -> iconKey 'error' and status_counts['error'] == 1."""
    trace = [
        _entry("resolve", 0, 40, status="ok"),
        _entry("graph_query", 40, 160, status="error"),
    ]
    timeline = build_tool_timeline(trace)

    assert timeline.steps[1]["iconKey"] == "error"
    assert timeline.status_counts["error"] == 1
    assert timeline.status_counts == {"ok": 1, "error": 1}


def test_unknown_tool_name_falls_back_to_the_name_as_label() -> None:
    """An unrecognised tool keeps its own name as the label (fallback / запасной)."""
    trace = [_entry("mystery_tool", 0, 10)]
    timeline = build_tool_timeline(trace)
    assert timeline.steps[0]["label"] == "mystery_tool"


def test_unknown_status_falls_back_to_pending_icon() -> None:
    """An unrecognised status -> 'pending' icon key (fallback / запасной)."""
    trace = [_entry("resolve", 0, 10, status="queued")]
    timeline = build_tool_timeline(trace)
    assert timeline.steps[0]["iconKey"] == "pending"


def test_steps_are_ordered_by_start_time_with_stable_step_index() -> None:
    """Out-of-order trace is sorted by startedAt; stepIndex is 0,1,2 in emitted order."""
    trace = [
        _entry("gap_scan", 200, 260),
        _entry("resolve", 0, 40),
        _entry("vector_search", 40, 100),
    ]
    timeline = build_tool_timeline(trace)

    assert [step["name"] for step in timeline.steps] == [
        "resolve",
        "vector_search",
        "gap_scan",
    ]
    assert [step["stepIndex"] for step in timeline.steps] == [0, 1, 2]
    assert [step["offsetMs"] for step in timeline.steps] == [0, 40, 200]


def test_equal_start_times_keep_insertion_order() -> None:
    """Equal startedAt values keep original order (stable sort / стабильная сортировка)."""
    trace = [
        _entry("evidence_check", 10, 20),
        _entry("graph_query", 10, 30),
    ]
    timeline = build_tool_timeline(trace)
    assert [step["name"] for step in timeline.steps] == ["evidence_check", "graph_query"]
    assert [step["stepIndex"] for step in timeline.steps] == [0, 1]


def test_as_dict_is_camel_case_and_span_consistent() -> None:
    """as_dict()['totalDurationMs'] == max(finishedAt) - min(startedAt) == sum of durations."""
    trace = [
        _entry("resolve", 0, 40),
        _entry("graph_query", 40, 160),
        _entry("evidence_check", 160, 175),
    ]
    timeline = build_tool_timeline(trace)
    payload = timeline.as_dict()

    assert set(payload) == {"steps", "totalDurationMs", "statusCounts"}
    # Non-overlapping calls: span == sum of per-call durations.
    span = 175 - 0
    sum_durations = 40 + 120 + 15
    assert payload["totalDurationMs"] == span == sum_durations == 175
    assert payload["statusCounts"] == {"ok": 3}
    assert [s["stepIndex"] for s in payload["steps"]] == [0, 1, 2]
    # as_dict steps are copies — mutating them must not touch the frozen timeline.
    payload["steps"][0]["label"] = "mutated"
    assert timeline.steps[0]["label"] == "resolved entities"


def test_reads_snake_case_trace_dicts_too() -> None:
    """Projection tolerates the raw tool_trace shape (tool/started_at/finished_at)."""
    trace = [
        {"tool": "resolve", "status": "ok", "started_at": 0, "finished_at": 40},
        {"tool": "graph_query", "status": "ok", "started_at": 40, "finished_at": 160},
    ]
    timeline = build_tool_timeline(trace)
    assert timeline.steps[0]["label"] == "resolved entities"
    assert timeline.steps[1]["offsetMs"] == 40
    assert timeline.total_duration_ms == 160
