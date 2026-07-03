"""Tests for §13.23 run metrics aggregator / тесты агрегатора метрик прогона.

Hand-checkable: every expected number is computed by eye from the fixtures.
"""

from __future__ import annotations

from agent_service.run_metrics import (
    RunMetrics,
    aggregate_runs,
    compute_run_metrics,
)


def _state() -> dict:
    """A run with 3 tool calls (one errored) and one unsupported claim."""
    return {
        "tool_trace": [
            {"tool": "a", "status": "ok", "duration_ms": 10},
            {"tool": "b", "status": "error", "duration_ms": 20},
            {"tool": "c", "status": "ok", "duration_ms": 30},
        ],
        "verifier_attempts": 2,
        "interrupt_request": {"reason": "clarify"},
        "verifier_report": {
            "violations": [
                {"id": "v1", "severity": "unsupported"},
                {"id": "v2", "severity": "style"},
                {"id": "v3", "severity": "missing_evidence"},
            ]
        },
    }


def test_tool_calls_and_errors_counted() -> None:
    """(1) 3 trace entries, one status 'error' → tool_calls==3, tool_errors==1."""
    m = compute_run_metrics(_state())
    assert m.tool_calls == 3
    assert m.tool_errors == 1


def test_total_tool_ms_sums_durations() -> None:
    """(2) total_tool_ms sums the entries' duration_ms (10+20+30==60)."""
    m = compute_run_metrics(_state())
    assert m.total_tool_ms == 60.0


def test_verifier_attempts_read_straight() -> None:
    """(3) verifier_attempts is read verbatim from state."""
    assert compute_run_metrics(_state()).verifier_attempts == 2
    assert compute_run_metrics({}).verifier_attempts == 0


def test_interrupt_count_truthy_then_zero() -> None:
    """(4) interrupt_count==1 when interrupt_request truthy else 0."""
    assert compute_run_metrics(_state()).interrupt_count == 1
    assert compute_run_metrics({"interrupt_request": None}).interrupt_count == 0
    assert compute_run_metrics({}).interrupt_count == 0


def test_unsupported_claims_only_unsupported_severity() -> None:
    """(5) unsupported_claims counts only severity=='unsupported' rows (1 of 3)."""
    assert compute_run_metrics(_state()).unsupported_claims == 1


def test_aggregate_error_rate_over_two_runs() -> None:
    """(6) two runs with 1/0 errors on 2/2 calls → error_rate==0.25."""
    run_a = RunMetrics(2, 1, 0, 0, 0, 40.0)
    run_b = RunMetrics(2, 0, 0, 0, 0, 20.0)
    agg = aggregate_runs([run_a, run_b])
    assert agg["error_rate"] == 0.25


def test_aggregate_other_rates() -> None:
    """Retry/interrupt/unsupported/avg rates over the same two runs."""
    run_a = RunMetrics(2, 1, 2, 1, 1, 40.0)
    run_b = RunMetrics(2, 0, 0, 0, 0, 20.0)
    agg = aggregate_runs([run_a, run_b])
    assert agg["retry_rate"] == 0.5
    assert agg["interrupt_rate"] == 0.5
    assert agg["unsupported_rate"] == 0.5
    assert agg["avg_tool_ms"] == 15.0  # (40+20)/(2+2)


def test_aggregate_empty_is_all_zero_floats() -> None:
    """(7) aggregate_runs([]) returns all-zero floats without ZeroDivisionError."""
    agg = aggregate_runs([])
    assert agg == {
        "error_rate": 0.0,
        "retry_rate": 0.0,
        "interrupt_rate": 0.0,
        "unsupported_rate": 0.0,
        "avg_tool_ms": 0.0,
    }
    assert all(isinstance(v, float) for v in agg.values())


def test_as_dict_round_trips_every_field() -> None:
    """(8) as_dict round-trips every field 1:1."""
    m = RunMetrics(
        tool_calls=3,
        tool_errors=1,
        verifier_attempts=2,
        interrupt_count=1,
        unsupported_claims=1,
        total_tool_ms=60.0,
    )
    d = m.as_dict()
    assert d == {
        "tool_calls": 3,
        "tool_errors": 1,
        "verifier_attempts": 2,
        "interrupt_count": 1,
        "unsupported_claims": 1,
        "total_tool_ms": 60.0,
    }
    assert RunMetrics(**d) == m
