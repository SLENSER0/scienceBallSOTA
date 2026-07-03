"""Spec-exact §12.17 retrieval trace: debug record of one hybrid query.

Лёгкий трейсер для отладки гибридного запроса (§12): фиксирует, какие каналы
(dense/sparse/bm25/graph…) отработали, сколько кандидатов вернул каждый, сколько
осталось после fusion, и тайминги (мс) по каждому каналу + суммарный ``total``.

Flow (builder → frozen trace):

    b = TraceBuilder("query text")
    b.start_channel("dense"); ...; b.record("dense", 20)
    b.start_channel("bm25");  ...; b.record("bm25", 15)
    trace = b.finish(n_fused=8)   # n_candidates == 35, timings["total"] set

Pure python — no store/graph access; callers feed the candidate counts they got
from each retriever. Kuzu note: custom node props are not queryable columns —
callers RETURN base columns and read the rest via ``get_node()`` upstream; this
module only records the resulting counts/timings, never touches the graph.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = ["ChannelTrace", "RetrievalTrace", "TraceBuilder"]

# Milliseconds per second — тайминги хранятся в мс для читаемости в UI/логах.
_MS_PER_SEC: float = 1000.0

# Reserved key in ``timings`` for the whole-query wall time (§12.17).
_TOTAL_KEY: str = "total"


@dataclass(frozen=True)
class ChannelTrace:
    """One channel leg of a hybrid query: имя, число кандидатов, elapsed (мс)."""

    name: str
    n_candidates: int
    elapsed_ms: float

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug (§12.17)."""
        return {
            "name": self.name,
            "n_candidates": self.n_candidates,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class RetrievalTrace:
    """Immutable debug trace of one hybrid retrieval (§12.17).

    ``channels`` — по одному :class:`ChannelTrace` на канал (в порядке записи).
    ``n_candidates`` — сумма кандидатов по всем каналам (до fusion). ``n_fused`` —
    сколько осталось после слияния/дедупа. ``timings`` — ``{channel: ms, …,
    "total": ms}`` (суммарное время запроса под ключом ``"total"``).
    """

    query: str
    channels: list[ChannelTrace] = field(default_factory=list)
    n_candidates: int = 0
    n_fused: int = 0
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def channel_names(self) -> list[str]:
        """Channel names in the order they were recorded."""
        return [c.name for c in self.channels]

    def as_dict(self) -> dict:
        """Plain-dict projection (channels → list of dicts, timings copied)."""
        return {
            "query": self.query,
            "channels": [c.as_dict() for c in self.channels],
            "n_candidates": self.n_candidates,
            "n_fused": self.n_fused,
            "timings": dict(self.timings),
        }


class TraceBuilder:
    """Mutable accumulator that produces a frozen :class:`RetrievalTrace` (§12.17).

    ``clock`` — монотонные секунды (по умолчанию :func:`time.perf_counter`);
    инъекция часов делает тайминги детерминированными для тестов. Каждый канал:
    :meth:`start_channel` (засечь старт) → :meth:`record` (закрыть, посчитать мс);
    :meth:`finish` замораживает трейс и добавляет суммарный ``total``.
    """

    def __init__(self, query: str, *, clock: Callable[[], float] = time.perf_counter) -> None:
        self._query = query
        self._clock = clock
        self._start = clock()
        self._channels: list[ChannelTrace] = []
        self._channel_starts: dict[str, float] = {}

    def start_channel(self, name: str) -> None:
        """Mark the wall-clock start of channel ``name`` (§12.17).

        Повторный старт того же канала (без :meth:`record`) — ошибка.
        """
        if name in self._channel_starts:
            raise ValueError(f"channel already started: {name!r}")
        self._channel_starts[name] = self._clock()

    def record(self, name: str, n_candidates: int) -> ChannelTrace:
        """Close channel ``name``: захватить число кандидатов и elapsed (мс).

        Требует предшествующего :meth:`start_channel`. Возвращает записанный
        :class:`ChannelTrace` (он же добавляется в трейс, порядок — по записи).
        """
        if name not in self._channel_starts:
            raise ValueError(f"channel not started: {name!r}")
        if n_candidates < 0:
            raise ValueError(f"n_candidates must be >= 0, got {n_candidates!r}")
        started = self._channel_starts.pop(name)
        elapsed_ms = (self._clock() - started) * _MS_PER_SEC
        channel = ChannelTrace(name=name, n_candidates=int(n_candidates), elapsed_ms=elapsed_ms)
        self._channels.append(channel)
        return channel

    def finish(self, n_fused: int) -> RetrievalTrace:
        """Freeze the trace: sum candidates, collect timings, record ``n_fused``.

        ``n_candidates`` — сумма по каналам; ``timings`` — ``{channel: ms}`` плюс
        ``"total"`` (полное время запроса от конструктора до :meth:`finish`).
        """
        if n_fused < 0:
            raise ValueError(f"n_fused must be >= 0, got {n_fused!r}")
        total_ms = (self._clock() - self._start) * _MS_PER_SEC
        n_candidates = sum(c.n_candidates for c in self._channels)
        timings: dict[str, float] = {c.name: c.elapsed_ms for c in self._channels}
        timings[_TOTAL_KEY] = total_ms
        return RetrievalTrace(
            query=self._query,
            channels=list(self._channels),
            n_candidates=n_candidates,
            n_fused=int(n_fused),
            timings=timings,
        )
