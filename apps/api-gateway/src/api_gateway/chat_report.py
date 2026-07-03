"""Chat message report export in JSON and Markdown (§14.4).

Сборка отчёта по сообщению чата: вопрос, краткое резюме, эксперименты,
доказательства, граф, пробелы и противоречия. Отчёт — неизменяемый frozen
dataclass с :meth:`ChatReport.as_dict`, где кортежи сериализуются в списки.
Модуль на чистом stdlib и обслуживает эндпоинт
``GET /chat/sessions/{id}/messages/{mid}/export``.

Build a per-chat-message report: the question, a summary, experiments, evidence,
the graph, gaps and contradictions. The report is an immutable frozen dataclass
with :meth:`ChatReport.as_dict` (tuples serialised as lists). Pure stdlib; backs
``GET /chat/sessions/{id}/messages/{mid}/export`` (§14.4).

Not to be confused with the retriever ``report_builder.py`` (§24 comparison
report) — this module is unrelated to it.

* :class:`ChatReport` — frozen report record with :meth:`as_dict`.
* :func:`build_report` — assemble a report from raw ``artifacts`` (safe defaults).
* :func:`to_markdown` — render a report as sectioned Markdown.
* :func:`to_json_dict` — render a report as a JSON-ready ``dict`` (``== as_dict``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatReport:
    """Неизменяемый отчёт по сообщению чата (§14.4).

    Immutable chat-message report. Collection fields are tuples so the record is
    hashable/frozen; :meth:`as_dict` serialises them back to lists for JSON.
    """

    session_id: str
    message_id: str
    question: str
    summary: str
    experiments: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    graph: dict[str, Any]
    gaps: tuple[dict[str, Any], ...]
    contradictions: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в JSON-совместимый dict (кортежи → списки).

        Serialise to a JSON-ready ``dict``; tuple fields become lists and each
        contained ``dict`` is shallow-copied so callers cannot mutate the report.
        """
        return {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "question": self.question,
            "summary": self.summary,
            "experiments": [dict(item) for item in self.experiments],
            "evidence": [dict(item) for item in self.evidence],
            "graph": dict(self.graph),
            "gaps": [dict(item) for item in self.gaps],
            "contradictions": [dict(item) for item in self.contradictions],
        }


def _as_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    """Нормализовать значение в кортеж dict-ов (по умолчанию — пустой).

    Coerce an artifact value into a tuple of dicts; ``None``/missing → ``()``.
    """
    if not value:
        return ()
    return tuple(dict(item) for item in value)


def build_report(session_id: str, message_id: str, artifacts: dict[str, Any]) -> ChatReport:
    """Собрать :class:`ChatReport` из сырых артефактов (§14.4).

    Missing artifact keys default to empty tuples / empty dict / empty string, so
    a bare ``{}`` yields a fully-formed but empty report.
    """
    graph = artifacts.get("graph") or {}
    return ChatReport(
        session_id=session_id,
        message_id=message_id,
        question=str(artifacts.get("question", "") or ""),
        summary=str(artifacts.get("summary", "") or ""),
        experiments=_as_tuple(artifacts.get("experiments")),
        evidence=_as_tuple(artifacts.get("evidence")),
        graph=dict(graph),
        gaps=_as_tuple(artifacts.get("gaps")),
        contradictions=_as_tuple(artifacts.get("contradictions")),
    )


_NONE = "_none_"


def _render_experiments(rows: tuple[dict[str, Any], ...]) -> str:
    """Отрисовать эксперименты как markdown-таблицу (или ``_none_``).

    Render experiments as a Markdown table with a ``| id | ... |`` header; an
    empty tuple renders the placeholder ``_none_``.
    """
    if not rows:
        return _NONE
    columns: list[str] = ["id"]
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    for row in rows:
        cells = [str(row.get(col, "")) for col in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _render_items(rows: tuple[dict[str, Any], ...]) -> str:
    """Отрисовать список записей как markdown-буллеты (или ``_none_``).

    Render a list of dict items as Markdown bullets; empty → ``_none_``.
    """
    if not rows:
        return _NONE
    return "\n".join(f"- {row}" for row in rows)


def _render_graph(graph: dict[str, Any]) -> str:
    """Отрисовать граф как markdown (или ``_none_``).

    Render the graph dict as a Markdown code fence; empty → ``_none_``.
    """
    if not graph:
        return _NONE
    return f"```\n{graph}\n```"


def to_markdown(report: ChatReport) -> str:
    """Отрисовать отчёт как секционированный Markdown (§14.4).

    Sections in fixed order: Summary, Experiments (table), Evidence, Graph, Gaps,
    Contradictions. Empty sections render the placeholder ``_none_``.
    """
    summary = report.summary or _NONE
    sections = [
        f"# {report.question}" if report.question else "# Chat report",
        "",
        "## Summary",
        summary,
        "",
        "## Experiments",
        _render_experiments(report.experiments),
        "",
        "## Evidence",
        _render_items(report.evidence),
        "",
        "## Graph",
        _render_graph(report.graph),
        "",
        "## Gaps",
        _render_items(report.gaps),
        "",
        "## Contradictions",
        _render_items(report.contradictions),
        "",
    ]
    return "\n".join(sections)


def to_json_dict(report: ChatReport) -> dict[str, Any]:
    """Отрисовать отчёт как JSON-совместимый dict (``== as_dict``).

    Thin wrapper over :meth:`ChatReport.as_dict` for the export endpoint.
    """
    return report.as_dict()
