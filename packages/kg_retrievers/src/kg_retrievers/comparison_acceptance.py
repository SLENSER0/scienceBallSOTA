"""Comparison-table acceptance audit (§24.13).

Сравнительный анализ — validator for the ``technology_comparison_acceptance``
acceptance test. A technology comparison table is a mapping of rows to columns to
cells; every cell must be *backed* — it either carries a non-empty ``evidence_ids``
list or is explicitly marked as a gap (``gap=True``). A cell that is empty, or that
holds a bare ``value`` with neither evidence nor a gap marker, is *unbacked* and
fails the audit.

Read-only over plain dicts: this module never writes to the graph. Результат —
frozen :class:`AcceptanceReport` with ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptanceReport:
    """Outcome of a comparison-table acceptance audit (§24.13).

    ``invalid_cells`` holds ``(row, col)`` pairs for every unbacked cell.
    ``passed`` is True iff there are no invalid cells. Каждая ячейка учтена
    ровно один раз: ``evidence_cells + gap_cells + len(invalid_cells) == total_cells``.
    """

    passed: bool
    total_cells: int
    evidence_cells: int
    gap_cells: int
    invalid_cells: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_cells": self.total_cells,
            "evidence_cells": self.evidence_cells,
            "gap_cells": self.gap_cells,
            "invalid_cells": [list(pair) for pair in self.invalid_cells],
        }


def _has_evidence(cell: dict) -> bool:
    """True iff ``cell`` carries a non-empty ``evidence_ids`` list (§24.13)."""
    evidence = cell.get("evidence_ids")
    return isinstance(evidence, list) and len(evidence) > 0


def audit_comparison(table: dict[str, dict[str, dict]]) -> AcceptanceReport:
    """Audit a comparison ``table`` for cell backing (§24.13).

    Проверка приёмки сравнительной таблицы. ``table`` maps ``row -> col -> cell``.
    A cell is valid iff it has a non-empty ``evidence_ids`` list OR ``gap is True``.
    Evidence takes precedence over a gap marker when both are present, so each cell
    is counted exactly once. ``invalid_cells`` lists the ``(row, col)`` of every
    unbacked cell in row-then-column iteration order.
    """
    total_cells = 0
    evidence_cells = 0
    gap_cells = 0
    invalid_cells: list[tuple[str, str]] = []

    for row, columns in table.items():
        for col, cell in columns.items():
            total_cells += 1
            if _has_evidence(cell):
                evidence_cells += 1
            elif cell.get("gap") is True:
                gap_cells += 1
            else:
                invalid_cells.append((row, col))

    return AcceptanceReport(
        passed=not invalid_cells,
        total_cells=total_cells,
        evidence_cells=evidence_cells,
        gap_cells=gap_cells,
        invalid_cells=tuple(invalid_cells),
    )
