"""Hand-checked tests for spec-exact §12.17 retrieval trace (builder + frozen DTO).

Тайминги детерминированы через инъекцию фейковых часов: каждый ``clock()`` берёт
следующее значение из заранее заданного списка «секунд», так что elapsed_ms
считается вручную ((end - start) * 1000).
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.retrieval_trace import ChannelTrace, RetrievalTrace, TraceBuilder


class _FakeClock:
    """Deterministic monotonic clock: возвращает ticks[0], ticks[1], … по вызовам."""

    def __init__(self, ticks: list[float]) -> None:
        self._ticks = list(ticks)
        self._i = 0

    def __call__(self) -> float:
        value = self._ticks[self._i]
        self._i += 1
        return value


# ---------------------------------------------------------------------------
# TraceBuilder — channels, sums, n_fused
# ---------------------------------------------------------------------------


def test_builder_records_channel_names() -> None:
    """start_channel + record добавляет канал; имена идут в порядке записи."""
    clock = _FakeClock([0.0, 0.0, 0.1, 0.2])  # init, start(dense), record, finish
    b = TraceBuilder("q", clock=clock)
    b.start_channel("dense")
    ch = b.record("dense", 5)
    assert isinstance(ch, ChannelTrace)
    assert ch.name == "dense"
    assert ch.n_candidates == 5
    trace = b.finish(n_fused=5)
    assert trace.channel_names == ["dense"]
    assert trace.channels[0].name == "dense"


def test_n_candidates_is_summed_across_channels() -> None:
    """n_candidates == сумма кандидатов по всем каналам (20 + 15 + 5 == 40)."""
    # init, start(dense), record(dense), start(bm25), record(bm25),
    # start(graph), record(graph), finish
    clock = _FakeClock([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    b = TraceBuilder("q", clock=clock)
    b.start_channel("dense")
    b.record("dense", 20)
    b.start_channel("bm25")
    b.record("bm25", 15)
    b.start_channel("graph")
    b.record("graph", 5)
    trace = b.finish(n_fused=8)
    assert trace.n_candidates == 40  # 20 + 15 + 5
    assert trace.n_fused == 8


def test_n_fused_recorded_independently_of_candidates() -> None:
    """n_fused берётся из finish() и не зависит от суммы кандидатов."""
    clock = _FakeClock([0.0, 0.0, 0.0, 0.0])
    b = TraceBuilder("q", clock=clock)
    b.start_channel("dense")
    b.record("dense", 30)
    trace = b.finish(n_fused=7)
    assert trace.n_candidates == 30
    assert trace.n_fused == 7  # 7 survived fusion/dedup out of 30


# ---------------------------------------------------------------------------
# Timings (deterministic via fake clock)
# ---------------------------------------------------------------------------


def test_timings_captured_per_channel_and_total() -> None:
    """elapsed_ms = (end-start)*1000 per channel; timings['total'] — весь запрос."""
    # init=0.0, start(dense)=0.0, record(dense)=0.1 -> 100ms,
    # start(bm25)=0.2, record(bm25)=0.5 -> 300ms, finish=1.0 -> total 1000ms
    clock = _FakeClock([0.0, 0.0, 0.1, 0.2, 0.5, 1.0])
    b = TraceBuilder("q", clock=clock)
    b.start_channel("dense")
    dense = b.record("dense", 10)
    b.start_channel("bm25")
    bm25 = b.record("bm25", 4)
    trace = b.finish(n_fused=6)
    assert dense.elapsed_ms == pytest.approx(100.0, abs=1e-9)
    assert bm25.elapsed_ms == pytest.approx(300.0, abs=1e-9)
    assert trace.timings == {
        "dense": pytest.approx(100.0, abs=1e-9),
        "bm25": pytest.approx(300.0, abs=1e-9),
        "total": pytest.approx(1000.0, abs=1e-9),
    }


def test_timings_default_clock_produces_nonnegative_floats() -> None:
    """Без инъекции часов (perf_counter) тайминги — float >= 0 и есть 'total'."""
    b = TraceBuilder("q")  # real time.perf_counter
    b.start_channel("dense")
    b.record("dense", 3)
    trace = b.finish(n_fused=3)
    assert set(trace.timings) == {"dense", "total"}
    assert all(isinstance(v, float) and v >= 0.0 for v in trace.timings.values())


# ---------------------------------------------------------------------------
# Empty trace + multiple channels
# ---------------------------------------------------------------------------


def test_empty_trace_has_no_channels_and_only_total_timing() -> None:
    """finish() без каналов → channels=[], n_candidates=0, timings={'total': …}."""
    clock = _FakeClock([0.0, 2.0])  # init=0.0, finish=2.0 -> total 2000ms
    b = TraceBuilder("empty", clock=clock)
    trace = b.finish(n_fused=0)
    assert trace.query == "empty"
    assert trace.channels == []
    assert trace.channel_names == []
    assert trace.n_candidates == 0
    assert trace.n_fused == 0
    assert trace.timings == {"total": pytest.approx(2000.0, abs=1e-9)}


def test_multiple_channels_preserve_record_order() -> None:
    """Три канала записаны в порядке record(); порядок сохраняется в channels."""
    clock = _FakeClock([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    b = TraceBuilder("q", clock=clock)
    for name, n in [("sparse", 12), ("dense", 8), ("graph", 3)]:
        b.start_channel(name)
        b.record(name, n)
    trace = b.finish(n_fused=9)
    assert trace.channel_names == ["sparse", "dense", "graph"]
    assert [c.n_candidates for c in trace.channels] == [12, 8, 3]
    assert trace.n_candidates == 23  # 12 + 8 + 3


# ---------------------------------------------------------------------------
# as_dict projections
# ---------------------------------------------------------------------------


def test_as_dict_full_shape_and_copy_independence() -> None:
    """as_dict() рендерит channels как list-of-dicts; timings — независимая копия."""
    clock = _FakeClock([0.0, 0.0, 0.25, 1.0])  # dense 250ms, total 1000ms
    b = TraceBuilder("hello", clock=clock)
    b.start_channel("dense")
    b.record("dense", 2)
    trace = b.finish(n_fused=1)
    d = trace.as_dict()
    assert d == {
        "query": "hello",
        "channels": [{"name": "dense", "n_candidates": 2, "elapsed_ms": pytest.approx(250.0)}],
        "n_candidates": 2,
        "n_fused": 1,
        "timings": {"dense": pytest.approx(250.0), "total": pytest.approx(1000.0)},
    }
    # Mutating the projection must not touch the frozen trace.
    d["timings"]["dense"] = -1.0
    d["channels"].append({"name": "hacked"})
    assert trace.timings["dense"] == pytest.approx(250.0)
    assert trace.channel_names == ["dense"]


def test_channel_trace_as_dict() -> None:
    """ChannelTrace.as_dict() — плоский словарь name/n_candidates/elapsed_ms."""
    ch = ChannelTrace(name="bm25", n_candidates=7, elapsed_ms=12.5)
    assert ch.as_dict() == {"name": "bm25", "n_candidates": 7, "elapsed_ms": 12.5}


# ---------------------------------------------------------------------------
# Validation + immutability
# ---------------------------------------------------------------------------


def test_record_without_start_raises() -> None:
    """record() без предшествующего start_channel() → ValueError."""
    b = TraceBuilder("q", clock=_FakeClock([0.0]))
    with pytest.raises(ValueError, match="not started"):
        b.record("dense", 5)


def test_start_channel_twice_raises() -> None:
    """Повторный start_channel() до record() → ValueError."""
    b = TraceBuilder("q", clock=_FakeClock([0.0, 0.0, 0.0]))
    b.start_channel("dense")
    with pytest.raises(ValueError, match="already started"):
        b.start_channel("dense")


def test_negative_counts_rejected() -> None:
    """Отрицательные n_candidates и n_fused отвергаются."""
    b = TraceBuilder("q", clock=_FakeClock([0.0, 0.0, 0.0, 0.0]))
    b.start_channel("dense")
    with pytest.raises(ValueError, match="n_candidates must be"):
        b.record("dense", -1)
    b.record("dense", 0)
    with pytest.raises(ValueError, match="n_fused must be"):
        b.finish(n_fused=-3)


def test_retrieval_trace_is_frozen() -> None:
    """RetrievalTrace заморожен: переприсваивание поля → FrozenInstanceError."""
    trace = RetrievalTrace(query="q")
    with pytest.raises(dataclasses.FrozenInstanceError):
        trace.query = "other"  # type: ignore[misc]
