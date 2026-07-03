"""§17.7 Chat — таймлайн вызовов инструментов / tool-call timeline (SOTA #7).

Pure projection over an already-captured ``tool_trace`` list (список словарей
``ToolTraceEntry.as_dict()`` из ``tool_trace.py`` / a list of trace dicts). No timing,
no I/O, no side effects — given a captured trace we render the five §5.2.2 UI stages as
an ordered, labelled timeline the chat UI can draw (агент-прозрачность / agent
transparency).

Each trace dict is read tolerantly: the tool name comes from ``name`` (fallback
``tool``), the timestamps from ``startedAt`` / ``finishedAt`` (fallback
``started_at`` / ``finished_at``). This keeps the projection working whether the trace
was serialised camelCase or snake_case.

Exports:

* :data:`STEP_LABELS` — tool name -> human §5.2.2 UI stage label.
* :data:`STATUS_ICONS` — trace status -> icon key (``ok`` -> ``done`` и т.д.).
* :class:`ToolTimeline` — frozen timeline with a camelCase :meth:`~ToolTimeline.as_dict`.
* :func:`build_tool_timeline` — order a trace by start time and enrich each step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# §5.2.2 UI-стадии: имя инструмента -> человекочитаемая метка / tool name -> UI label.
STEP_LABELS: dict[str, str] = {
    "resolve": "resolved entities",
    "graph_query": "graph query",
    "vector_search": "vector search",
    "evidence_check": "evidence check",
    "gap_scan": "gap scan",
}

# Статус трассы -> ключ иконки / trace status -> icon key (пусто -> ожидание / pending).
STATUS_ICONS: dict[str, str] = {
    "ok": "done",
    "error": "error",
    "running": "running",
    "": "pending",
}

# Fallback icon key for an unknown / missing status (неизвестный статус -> ожидание).
_ICON_FALLBACK = "pending"


def _tool_name(entry: dict[str, Any]) -> str:
    """Read the tool name from a trace dict (``name`` первично, ``tool`` запасной)."""
    name = entry.get("name")
    if name is None:
        name = entry.get("tool")
    return "" if name is None else str(name)


def _started_at(entry: dict[str, Any]) -> float:
    """Read the start timestamp (``startedAt`` -> ``started_at`` -> 0)."""
    value = entry.get("startedAt", entry.get("started_at", 0))
    return float(value)


def _finished_at(entry: dict[str, Any]) -> float:
    """Read the finish timestamp (``finishedAt`` -> ``finished_at`` -> ``startedAt``)."""
    value = entry.get("finishedAt", entry.get("finished_at", _started_at(entry)))
    return float(value)


def _as_int_ms(value: float) -> int:
    """Normalise a timestamp/span to whole milliseconds (целые мс / integer ms)."""
    return int(value) if float(value).is_integer() else round(value)


@dataclass(frozen=True)
class ToolTimeline:
    """Ordered, labelled projection of a tool trace (§17.7).

    ``steps`` is a tuple of enriched trace dicts (each carries ``label``, ``iconKey``,
    ``offsetMs`` and ``stepIndex``), ``total_duration_ms`` is the wall span of the trace
    (``max(finishedAt) - min(startedAt)`` / без наложения == сумме длительностей) and
    ``status_counts`` tallies how many steps landed in each status.
    """

    steps: tuple[dict[str, Any], ...]
    total_duration_ms: int
    status_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a camelCase dict (``totalDurationMs`` / ``statusCounts`` — API shape)."""
        return {
            "steps": [dict(step) for step in self.steps],
            "totalDurationMs": self.total_duration_ms,
            "statusCounts": dict(self.status_counts),
        }


def build_tool_timeline(trace: list[dict[str, Any]]) -> ToolTimeline:
    """Project a captured ``trace`` into a :class:`ToolTimeline` (чистая проекция / pure).

    Steps are ordered by ``startedAt`` then by original position (stable — равные метки
    времени сохраняют порядок / equal timestamps keep insertion order). Each emitted step
    is a shallow copy of its trace dict enriched with:

    * ``label`` — §5.2.2 UI label via :data:`STEP_LABELS`, falling back to the tool name.
    * ``iconKey`` — status icon via :data:`STATUS_ICONS`, falling back to ``pending``.
    * ``offsetMs`` — ``startedAt`` minus the first step's ``startedAt`` (первый шаг == 0).
    * ``stepIndex`` — 0-based position in emission order.

    An empty trace yields ``total_duration_ms == 0``, ``steps == ()`` and
    ``status_counts == {}``.
    """
    if not trace:
        return ToolTimeline(steps=(), total_duration_ms=0, status_counts={})

    # Order by start time, keeping original index as a stable tie-breaker / стабильно.
    ordered = sorted(enumerate(trace), key=lambda pair: (_started_at(pair[1]), pair[0]))

    first_start = _started_at(ordered[0][1])
    steps: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for step_index, (_, entry) in enumerate(ordered):
        name = _tool_name(entry)
        status = str(entry.get("status", ""))
        enriched = dict(entry)
        enriched["label"] = STEP_LABELS.get(name, name)
        enriched["iconKey"] = STATUS_ICONS.get(status, _ICON_FALLBACK)
        enriched["offsetMs"] = _as_int_ms(_started_at(entry) - first_start)
        enriched["stepIndex"] = step_index
        steps.append(enriched)
        status_counts[status] = status_counts.get(status, 0) + 1

    span = max(_finished_at(e) for _, e in ordered) - min(_started_at(e) for _, e in ordered)
    total_duration_ms = _as_int_ms(span)

    return ToolTimeline(
        steps=tuple(steps),
        total_duration_ms=total_duration_ms,
        status_counts=status_counts,
    )
