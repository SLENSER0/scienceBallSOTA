"""Per-cell source count + confidence banding for comparison tables (§24.13).

Правило §24.13: обязательно показывать *source count* и *confidence* по каждой
ячейке сравнительной таблицы; если evidence нет — ячейка помечается как ``gap``.

The sibling :mod:`comparison_acceptance` audit only checks backed-vs-unbacked
(pass/fail) — it does *not* band confidence. This module fills that gap: it counts
the DISTINCT evidence ids per cell and maps the count to a confidence band, keeping
gap cells visible rather than dropping them.

Bands (по числу уникальных источников):

===============  =====
source_count     band
===============  =====
0                none
1                low
2-3              medium
>=4              high
===============  =====

Read-only over plain lists: this module never writes to the graph. Результат —
frozen :class:`CellConfidence` with ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass


def _band(source_count: int) -> str:
    """Map a distinct-source count to a confidence band (§24.13)."""
    if source_count <= 0:
        return "none"
    if source_count == 1:
        return "low"
    if source_count <= 3:
        return "medium"
    return "high"


@dataclass(frozen=True)
class CellConfidence:
    """Confidence verdict for one comparison-table cell (§24.13).

    ``source_count`` — число уникальных evidence ids. ``confidence`` is the band
    ('none'/'low'/'medium'/'high'). ``gap`` is True iff no evidence backs the cell
    (``source_count == 0``), so a gap cell is still reported, never dropped.
    """

    row: str
    col: str
    source_count: int
    confidence: str
    gap: bool

    def as_dict(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "source_count": self.source_count,
            "confidence": self.confidence,
            "gap": bool(self.gap),
        }


def score_cell(row: str, col: str, evidence_ids: list[str]) -> CellConfidence:
    """Score one cell's source count + confidence band (§24.13).

    ``source_count`` counts DISTINCT ``evidence_ids`` (duplicates collapse). A cell
    with zero sources is a ``gap``. Оценка одной ячейки: банд считается из числа
    уникальных источников.
    """
    source_count = len(set(evidence_ids))
    return CellConfidence(
        row=row,
        col=col,
        source_count=source_count,
        confidence=_band(source_count),
        gap=source_count == 0,
    )


def score_table(
    cells: dict[tuple[str, str], list[str]],
) -> tuple[CellConfidence, ...]:
    """Score every cell of a comparison ``table``, sorted by ``(row, col)`` (§24.13).

    ``cells`` maps ``(row, col) -> evidence_ids``. Каждая ячейка учтена, включая
    gap-ячейки: они не отбрасываются, а помечаются ``gap=True``. Порядок —
    детерминированный по (row, col).
    """
    scored = [score_cell(row, col, ev) for (row, col), ev in cells.items()]
    return tuple(sorted(scored, key=lambda c: (c.row, c.col)))
