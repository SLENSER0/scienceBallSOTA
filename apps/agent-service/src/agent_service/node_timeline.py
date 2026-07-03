"""§13.23 логирование / logging — per-node latency timeline.

Where :mod:`agent_service.run_metrics` folds a run into *run-level* counters
(tool calls, retries, interrupts), it never opens the box on **individual
graph nodes**: it has no notion of where a run spent its wall-clock time. This
module reconstructs that missing view — a per-node latency timeline — straight
from the ``node_enter``/``node_exit`` log records a run emits (§13.23).

Pure-python and deterministic: no clock, no store, no graph. Given an ordered
list of event dicts (``{'event','node','ts_ms'}``) it pairs each ``node_enter``
with the *next* matching ``node_exit`` of the same node, measures the span
(``exit.ts_ms - enter.ts_ms``, clamped at ``0.0``), and rolls the spans up into
a frozen :class:`Timeline` with the total elapsed and the slowest node. Every
number is hand-checkable, so the tests stay fully deterministic.

* :class:`NodeSpan` — one paired node visit (узел + длительность в мс).
* :class:`Timeline` — all spans in enter order plus ``total_ms``/``slowest``.
* :func:`build_timeline` — fold an event list into a :class:`Timeline`.
"""

from __future__ import annotations

from dataclasses import dataclass

# Log-record ``event`` markers bracketing one node visit (вход/выход узла).
_EVENT_ENTER = "node_enter"
_EVENT_EXIT = "node_exit"


@dataclass(frozen=True)
class NodeSpan:
    """One paired node visit (§13.23) / один интервал посещения узла.

    ``node`` is the graph node's name, ``duration_ms`` the elapsed wall-clock
    between its ``node_enter`` and the matching ``node_exit`` (clamped at
    ``0.0`` — время не бывает отрицательным / never negative).
    """

    node: str
    duration_ms: float

    def as_dict(self) -> dict[str, str | float]:
        """Serialise to ``{'node','duration_ms'}`` (round-trips 1:1 / без потерь)."""
        return {"node": self.node, "duration_ms": self.duration_ms}


@dataclass(frozen=True)
class Timeline:
    """Per-node latency timeline of one run (§13.23) / таймлайн задержек прогона.

    ``spans`` holds every paired :class:`NodeSpan` in ``node_enter`` order,
    ``total_ms`` sums their durations and ``slowest`` names the max-duration
    node (first on ties, ``None`` when there are no spans / нет интервалов).
    """

    spans: tuple[NodeSpan, ...]
    total_ms: float
    slowest: str | None

    def as_dict(self) -> dict[str, object]:
        """Serialise every field; ``spans`` becomes a list of per-span dicts."""
        return {
            "spans": [s.as_dict() for s in self.spans],
            "total_ms": self.total_ms,
            "slowest": self.slowest,
        }


def build_timeline(events: list[dict]) -> Timeline:
    """Fold ``node_enter``/``node_exit`` records into a :class:`Timeline` (§13.23).

    ``events`` is an ordered list of ``{'event','node','ts_ms'}`` dicts. Each
    ``node_enter`` is paired with the **next** ``node_exit`` of the same node
    that follows it; the span duration is ``exit.ts_ms - enter.ts_ms`` clamped
    at ``0.0`` (an exit timestamped before its enter yields ``0.0``). An enter
    with no later matching exit contributes no span (никакого интервала).
    ``total_ms`` sums the span durations and ``slowest`` is the max-duration
    node (first on ties, ``None`` when empty). Spans keep ``node_enter`` order.
    """
    # Matched spans keyed by their ``node_enter`` position so the final list
    # keeps enter order even when exits arrive interleaved (порядок входов).
    matched: list[tuple[int, NodeSpan]] = []
    # Pending enters per node, oldest-first: (enter_index, enter_ts) / очередь.
    pending: dict[str, list[tuple[int, float]]] = {}

    for enter_index, event in enumerate(events):
        kind = event.get("event")
        node = event.get("node")
        ts_ms = float(event.get("ts_ms", 0.0))

        if kind == _EVENT_ENTER:
            pending.setdefault(node, []).append((enter_index, ts_ms))
        elif kind == _EVENT_EXIT:
            opened = pending.get(node)
            if opened:
                open_index, enter_ts = opened.pop(0)
                duration_ms = max(0.0, ts_ms - enter_ts)
                matched.append((open_index, NodeSpan(node=node, duration_ms=duration_ms)))

    matched.sort(key=lambda item: item[0])
    spans = [span for _, span in matched]

    total_ms = float(sum(s.duration_ms for s in spans))

    slowest: str | None = None
    best = float("-inf")
    for span in spans:
        if span.duration_ms > best:
            best = span.duration_ms
            slowest = span.node

    return Timeline(spans=tuple(spans), total_ms=total_ms, slowest=slowest)
