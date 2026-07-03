"""Structured comparison-report builder (§24.16).

Сравнительный отчёт по технологическим решениям — takes already-resolved solution
records and a fixed list of metrics (метрики) and lays them out as a comparison
table (таблица сравнения): one column per metric, one row per solution.

Each cell is *never* empty (§24.13 invariant «заполнено или пробел»): it is either
an evidence-backed value ``{value, unit, evidence_ids}`` or a gap marker
``{gap: True}``. A metric that is missing — or present without a value or without any
supporting evidence — resolves to a gap cell (пробел), so a value cell is always
evidence-backed.

Alongside the table the report carries:

- ``sources`` — the deduplicated Evidence ids (источники) backing every value cell;
- ``gaps`` — the (solution, metric) pairs that came out as gaps (пробелы).

Pure-python and deterministic: no graph store, no LLM. Results are frozen dataclasses
exposing ``as_dict()`` / ``from_dict()`` for JSON transport, plus a ``to_markdown``
renderer producing an RU markdown table with a Sources section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Marker key identifying a gap cell (пробел) in the serialised table (§24.13).
GAP_KEY = "gap"

# Dash rendered in place of a gap cell in the markdown table (тире).
GAP_DASH = "—"

# Header of the first (solution-name) column in the markdown table.
SOLUTION_HEADER = "Решение"

# Title of the sources section in the markdown output (Источники / Sources).
SOURCES_HEADER = "Источники"


@dataclass(frozen=True)
class ReportCell:
    """One table cell — an evidence-backed value or a gap (§24.16 / §24.13).

    A cell is never empty. When ``is_gap`` is true it serialises to ``{gap: True}``
    (a пробел); otherwise it is an evidence-backed value serialising to
    ``{value, unit, evidence_ids}`` whose ``evidence_ids`` is guaranteed non-empty.
    """

    metric: str
    is_gap: bool
    value: Any = None
    unit: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{gap: True}`` or ``{value, unit, evidence_ids}`` (§24.13)."""
        if self.is_gap:
            return {GAP_KEY: True}
        return {
            "value": self.value,
            "unit": self.unit,
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, metric: str, data: dict[str, Any]) -> ReportCell:
        """Rebuild a cell from its serialised form (inverse of :meth:`as_dict`)."""
        if data.get(GAP_KEY):
            return cls(metric=metric, is_gap=True)
        return cls(
            metric=metric,
            is_gap=False,
            value=data.get("value"),
            unit=data.get("unit"),
            evidence_ids=tuple(data.get("evidence_ids", ())),
        )


@dataclass(frozen=True)
class GapEntry:
    """A single gap cell located by its solution and metric (§24.16 / §24.13)."""

    solution_id: str
    solution_name: str
    metric: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{solution_id, solution_name, metric, gap: True}``."""
        return {
            "solution_id": self.solution_id,
            "solution_name": self.solution_name,
            "metric": self.metric,
            GAP_KEY: True,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GapEntry:
        """Rebuild a gap entry from its serialised form."""
        return cls(
            solution_id=str(data.get("solution_id", "")),
            solution_name=str(data.get("solution_name", "")),
            metric=str(data.get("metric", "")),
        )


@dataclass(frozen=True)
class ReportRow:
    """One solution's row across every metric column (§24.16).

    ``cells`` is aligned to the report's ``columns`` order — exactly one cell per
    metric, each either a value cell or a gap cell.
    """

    solution_id: str
    solution_name: str
    cells: tuple[ReportCell, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{id, name, cells: {metric: cell}}`` (§24.16)."""
        return {
            "id": self.solution_id,
            "name": self.solution_name,
            "cells": {c.metric: c.as_dict() for c in self.cells},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], columns: tuple[str, ...]) -> ReportRow:
        """Rebuild a row, ordering its cells by ``columns`` (inverse of as_dict)."""
        raw_cells = data.get("cells", {}) or {}
        cells = tuple(ReportCell.from_dict(m, raw_cells.get(m, {GAP_KEY: True})) for m in columns)
        return cls(
            solution_id=str(data.get("id", "")),
            solution_name=str(data.get("name", "")),
            cells=cells,
        )


@dataclass(frozen=True)
class ComparisonReport:
    """A structured comparison report (§24.16).

    Attributes:
        columns: the metric names (метрики) — the table's ordered columns.
        rows: one :class:`ReportRow` per solution, cells aligned to ``columns``.
        sources: deduplicated Evidence ids (источники) backing all value cells, sorted.
        gaps: every gap cell (пробел) as a :class:`GapEntry`, in row/column order.
    """

    columns: tuple[str, ...]
    rows: tuple[ReportRow, ...] = ()
    sources: tuple[str, ...] = ()
    gaps: tuple[GapEntry, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        """Serialise the whole report to a JSON-ready dict (§24.16)."""
        return {
            "columns": list(self.columns),
            "rows": [r.as_dict() for r in self.rows],
            "sources": list(self.sources),
            "gaps": [g.as_dict() for g in self.gaps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComparisonReport:
        """Rebuild a report from :meth:`as_dict` output (round-trip stable)."""
        columns = tuple(data.get("columns", ()))
        rows = tuple(ReportRow.from_dict(r, columns) for r in data.get("rows", ()))
        return cls(
            columns=columns,
            rows=rows,
            sources=tuple(data.get("sources", ())),
            gaps=tuple(GapEntry.from_dict(g) for g in data.get("gaps", ())),
        )


def _clean_evidence(raw: Any) -> tuple[str, ...]:
    """Normalise an ``evidence_ids`` value into a sorted, deduped id tuple."""
    if isinstance(raw, str):
        return (raw,) if raw else ()
    if not isinstance(raw, (list, tuple, set)):
        return ()
    return tuple(sorted({str(x) for x in raw if x}))


def _build_cell(metric: str, entry: Any) -> ReportCell:
    """Turn one solution's metric entry into a value or gap cell (§24.13).

    A value cell requires a non-``None`` ``value`` *and* at least one evidence id;
    anything else (missing metric, no value, or no evidence) becomes a gap cell.
    """
    if not isinstance(entry, dict):
        return ReportCell(metric=metric, is_gap=True)
    value = entry.get("value")
    evidence = _clean_evidence(entry.get("evidence_ids"))
    if value is None or not evidence:
        return ReportCell(metric=metric, is_gap=True)
    unit = entry.get("unit")
    return ReportCell(
        metric=metric,
        is_gap=False,
        value=value,
        unit=str(unit) if unit is not None else None,
        evidence_ids=evidence,
    )


def build_comparison_report(
    solutions: list[dict[str, Any]], metrics: list[str]
) -> ComparisonReport:
    """Build a structured comparison report over ``solutions`` × ``metrics`` (§24.16).

    Each solution dict is shaped ``{id, name, metrics: {metric: {value, unit,
    evidence_ids}}}``. For every metric the cell is either an evidence-backed value or
    a gap — never empty (§24.13). ``sources`` collects the deduped evidence ids across
    all value cells; ``gaps`` collects every gap cell. Empty ``solutions`` yields an
    empty report that still carries ``columns`` (graceful).
    """
    columns = tuple(metrics)
    rows: list[ReportRow] = []
    sources: set[str] = set()
    gaps: list[GapEntry] = []

    for sol in solutions:
        sid = str(sol.get("id", ""))
        name = str(sol.get("name") or sid)
        metric_map = sol.get("metrics") or {}
        cells: list[ReportCell] = []
        for metric in columns:
            cell = _build_cell(metric, metric_map.get(metric))
            cells.append(cell)
            if cell.is_gap:
                gaps.append(GapEntry(solution_id=sid, solution_name=name, metric=metric))
            else:
                sources.update(cell.evidence_ids)
        rows.append(ReportRow(solution_id=sid, solution_name=name, cells=tuple(cells)))

    return ComparisonReport(
        columns=columns,
        rows=tuple(rows),
        sources=tuple(sorted(sources)),
        gaps=tuple(gaps),
    )


def _render_cell(cell: ReportCell) -> str:
    """Render one cell for the markdown table: ``value unit`` or a gap dash (§24.16)."""
    if cell.is_gap:
        return GAP_DASH
    if cell.unit:
        return f"{cell.value} {cell.unit}"
    return f"{cell.value}"


def to_markdown(report: ComparisonReport) -> str:
    """Render a :class:`ComparisonReport` as an RU markdown table + Sources (§24.16).

    Produces a header row (``Решение`` + metric columns), a separator row, then one
    row per solution with ``—`` for gap cells, followed by an ``## Источники`` section
    listing the deduped sources (or a dash when there are none).
    """
    header = [SOLUTION_HEADER, *report.columns]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for row in report.rows:
        cells = [row.solution_name, *(_render_cell(c) for c in row.cells)]
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append(f"## {SOURCES_HEADER}")
    if report.sources:
        lines.extend(f"- {src}" for src in report.sources)
    else:
        lines.append(f"- {GAP_DASH}")

    return "\n".join(lines) + "\n"
