"""Tests for §13.23 per-node latency timeline / таймлайн задержек узлов.

Hand-checkable, fully deterministic: every timestamp and duration below is a
plain integer millisecond, so each asserted span/total is arithmetic on the
literals — no clock, no store, no graph.
"""

from __future__ import annotations

from agent_service.node_timeline import NodeSpan, Timeline, build_timeline


def _enter(node: str, ts_ms: float) -> dict:
    return {"event": "node_enter", "node": node, "ts_ms": ts_ms}


def _exit(node: str, ts_ms: float) -> dict:
    return {"event": "node_exit", "node": node, "ts_ms": ts_ms}


def test_single_pair_duration() -> None:
    # enter@100 / exit@175 → one span of 175-100 == 75.0 ms.
    tl = build_timeline([_enter("retrieve", 100.0), _exit("retrieve", 175.0)])
    assert len(tl.spans) == 1
    assert tl.spans[0] == NodeSpan(node="retrieve", duration_ms=75.0)
    assert tl.spans[0].duration_ms == 75.0


def test_total_ms_sums_spans() -> None:
    # Two spans: 75 (a) + 40 (b) → total 115.0.
    tl = build_timeline(
        [
            _enter("a", 0.0),
            _exit("a", 75.0),
            _enter("b", 200.0),
            _exit("b", 240.0),
        ]
    )
    assert tl.total_ms == 115.0
    assert tl.total_ms == sum(s.duration_ms for s in tl.spans)


def test_slowest_is_longer_duration_node() -> None:
    tl = build_timeline(
        [
            _enter("fast", 0.0),
            _exit("fast", 10.0),
            _enter("slow", 100.0),
            _exit("slow", 260.0),
        ]
    )
    assert tl.slowest == "slow"


def test_enter_without_exit_contributes_no_span() -> None:
    # 'lonely' never exits → only the a-pair yields a span.
    tl = build_timeline(
        [
            _enter("lonely", 0.0),
            _enter("a", 5.0),
            _exit("a", 30.0),
        ]
    )
    assert [s.node for s in tl.spans] == ["a"]
    assert tl.spans[0].duration_ms == 25.0


def test_exit_before_enter_clamps_to_zero() -> None:
    # exit ts precedes enter ts → duration clamped at 0.0, never negative.
    tl = build_timeline([_enter("x", 500.0), _exit("x", 400.0)])
    assert tl.spans[0].duration_ms == 0.0
    assert tl.total_ms == 0.0


def test_spans_preserve_enter_order_under_interleave() -> None:
    # Enter order A, B; exit order B, A → spans stay in enter order A, B.
    tl = build_timeline(
        [
            _enter("A", 0.0),
            _enter("B", 10.0),
            _exit("B", 40.0),
            _exit("A", 100.0),
        ]
    )
    assert [s.node for s in tl.spans] == ["A", "B"]
    assert tl.spans[0].duration_ms == 100.0
    assert tl.spans[1].duration_ms == 30.0


def test_slowest_first_on_ties() -> None:
    # Two equal-duration spans → the earlier-entered node wins the tie.
    tl = build_timeline(
        [
            _enter("first", 0.0),
            _exit("first", 50.0),
            _enter("second", 100.0),
            _exit("second", 150.0),
        ]
    )
    assert tl.slowest == "first"


def test_empty_events() -> None:
    tl = build_timeline([])
    assert tl == Timeline(spans=(), total_ms=0.0, slowest=None)
    assert tl.spans == ()
    assert tl.total_ms == 0.0
    assert tl.slowest is None


def test_timeline_as_dict_spans_is_list_of_dicts() -> None:
    tl = build_timeline([_enter("n", 0.0), _exit("n", 20.0)])
    d = tl.as_dict()
    assert d["spans"] == [{"node": "n", "duration_ms": 20.0}]
    assert isinstance(d["spans"], list)
    assert d["total_ms"] == 20.0
    assert d["slowest"] == "n"


def test_node_span_as_dict() -> None:
    span = NodeSpan(node="q", duration_ms=12.5)
    assert span.as_dict() == {"node": "q", "duration_ms": 12.5}
