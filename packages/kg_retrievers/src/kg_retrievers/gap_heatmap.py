"""Gap heat-map — count gaps across a two-axis grid (§15.15).

The gap scanner (:mod:`kg_retrievers.gap_analysis`, §15) materializes many
``Gap`` nodes; §15.6 (:mod:`kg_retrievers.gap_dashboard`) rolls them into scalar
buckets and §15.12 (:mod:`kg_retrievers.gap_clustering`) groups the same missing
corner. §15.15 lays the gaps onto a **two-dimensional grid** — тепловая карта —
so a curator can *see* where the holes concentrate: which material lacks which
property, which domain lacks which type, and so on.

Each gap contributes ``1`` to the cell ``(row, col)`` where ``row`` / ``col`` are
read from the gap along a configurable pair of axes (default ``material`` ×
``property``). An axis value is resolved by trying the bare axis name first
(``gap["material"]``) then the ``<axis>_id`` form (``gap["material_id"]``) —
gap dicts in this codebase carry the ``_id`` variant, но обе формы поддержаны.
A gap missing that dimension lands in the :data:`MISSING_KEY` bucket, so nothing
is silently dropped (§15.15).

Pure python — no graph or store access; the caller assembles the gap dicts
(shape ``{id?, material_id?, property_id?, domain?, type?, ...}``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# Bucket for a gap that carries no value on a given axis (§15.15) — пустая ось.
MISSING_KEY = "(missing)"


@dataclass(frozen=True)
class Heatmap:
    """A counted two-axis grid of gaps (§15.15).

    ``row_keys`` / ``col_keys`` are the sorted, de-duplicated axis labels;
    ``cells`` maps a ``(row, col)`` pair to its gap count (only non-zero cells are
    stored); ``max_count`` is the largest single-cell count (``0`` for an empty
    map). ``rows`` / ``cols`` echo the axis names the grid was built on.
    """

    rows: str
    cols: str
    row_keys: tuple[str, ...]
    col_keys: tuple[str, ...]
    cells: dict[tuple[str, str], int]
    max_count: int

    def count(self, row: str, col: str) -> int:
        """Gap count at ``(row, col)`` — ``0`` when the cell is empty."""
        return self.cells.get((row, col), 0)

    def as_dict(self) -> dict:
        """JSON-friendly view; ``cells`` becomes a sorted list of row/col/count."""
        cells = [
            {"row": row, "col": col, "count": self.cells[(row, col)]}
            for row, col in sorted(self.cells)
        ]
        return {
            "rows": self.rows,
            "cols": self.cols,
            "row_keys": list(self.row_keys),
            "col_keys": list(self.col_keys),
            "cells": cells,
            "max_count": self.max_count,
        }


def _axis_value(gap: dict, axis: str) -> str:
    """Resolve ``gap``'s value on ``axis`` (bare name, then ``<axis>_id`` form).

    Returns the trimmed string value, or :data:`MISSING_KEY` when neither key holds
    a non-blank string.
    """
    for key in (axis, f"{axis}_id"):
        value = gap.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return MISSING_KEY


def build_heatmap(
    gaps: list[dict],
    *,
    rows: str = "material",
    cols: str = "property",
) -> Heatmap:
    """Count ``gaps`` into a ``rows`` × ``cols`` :class:`Heatmap` (§15.15).

    Every gap adds ``1`` to the cell keyed by its ``rows`` and ``cols`` axis
    values (:func:`_axis_value`); a gap missing either dimension counts into the
    :data:`MISSING_KEY` bucket on that axis. ``row_keys`` / ``col_keys`` are sorted
    for a deterministic grid, and ``max_count`` is the busiest cell. ``[]`` yields
    an empty map with ``max_count == 0``.
    """
    counter: Counter[tuple[str, str]] = Counter()
    for gap in gaps:
        counter[(_axis_value(gap, rows), _axis_value(gap, cols))] += 1
    cells = dict(counter)
    row_keys = tuple(sorted({row for row, _ in cells}))
    col_keys = tuple(sorted({col for _, col in cells}))
    max_count = max(cells.values(), default=0)
    return Heatmap(
        rows=rows,
        cols=cols,
        row_keys=row_keys,
        col_keys=col_keys,
        cells=cells,
        max_count=max_count,
    )
