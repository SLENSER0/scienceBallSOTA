"""§13.22 tool-call timeline labels (§5.2.2) / метки временной шкалы вызовов инструментов.

``stream_events.py`` emits machine ``tool_start`` / ``tool_end`` pairs keyed by the raw
tool name; those frames are precise but not human. §5.2.2 shows the user a *labelled*
timeline of what the agent actually did — "resolved entities → graph query → vector
search → evidence check → gap scan" — grouping many low-level tools under a handful of
readable phases.

This module is the pure mapping from a ``tool_trace`` (list of ``{'tool', 'status'}``
dicts, §13.11) to that human timeline. No store, no LLM, no clock — same trace in, same
:class:`TimelineStep` list out, so the §5.2.2 contract is hand-checkable in a unit test.

Каждая запись трассы / each trace entry maps its ``tool`` through :data:`LABELS` to a
human phase label (unknown tools fall back to their own name) and carries the entry's
``status`` (default ``'ok'``). Step order matches trace order exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["LABELS", "TimelineStep", "build_tool_timeline"]

#: Raw tool name → human §5.2.2 phase label (замкнутый словарь / closed mapping).
#: Tools absent here fall back to their own name in :func:`build_tool_timeline`.
LABELS: dict[str, str] = {
    "resolve_entities": "resolved entities",
    "run_cypher_template": "graph query",
    "run_cypher_readonly": "graph query",
    "find_graph_paths": "graph query",
    "vector_search_qdrant": "vector search",
    "keyword_search_opensearch": "vector search",
    "hybrid_search": "vector search",
    "get_evidence_by_ids": "evidence check",
    "get_document_snippet": "evidence check",
    "scan_gaps": "gap scan",
    "detect_contradictions": "gap scan",
}


@dataclass(frozen=True)
class TimelineStep:
    """One §5.2.2 timeline phase: a human ``label``, the raw ``tool``, and its ``status``.

    Frozen and JSON-serialisable via :meth:`as_dict`; the builder never mutates a step
    after creation (шаги неизменяемы / steps are immutable).
    """

    label: str
    tool: str
    status: str

    def as_dict(self) -> dict[str, str]:
        """Serialise to ``{'label': label, 'tool': tool, 'status': status}`` (3-key shape)."""
        return {"label": self.label, "tool": self.tool, "status": self.status}


def build_tool_timeline(tool_trace: list[dict[str, Any]]) -> list[TimelineStep]:
    """Map a raw ``tool_trace`` to the human §5.2.2 timeline, preserving order.

    Для каждой записи / for each entry: ``tool`` → :data:`LABELS` label (falling back to
    the tool name for unknown tools) and ``status`` (default ``'ok'``).
    """
    steps: list[TimelineStep] = []
    for entry in tool_trace:
        tool = str(entry["tool"])
        label = LABELS.get(tool, tool)
        status = str(entry.get("status", "ok"))
        steps.append(TimelineStep(label=label, tool=tool, status=status))
    return steps
