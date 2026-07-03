"""Table-structure benchmark — TEDS-lite cell-grid similarity (§23.34/§23.31).

Deterministic, hand-checkable table-structure scoring for OmniDocBench table
acceptance. The ``table_contract`` / ``table_extractor`` in ``kg_extractors``
*produce* tables but never score them against gold; this module fills that gap
with a TEDS-style («tree-edit-distance similarity») metric collapsed to an
aligned-grid comparison — простое посеточное сравнение ячеек.

A table is a list-of-rows of cell strings. Two facets are scored:

* **structure_similarity** — how well the *shapes* line up: the number of grid
  positions that both tables occupy, divided by the larger cell count. Two
  identically-shaped tables score ``1.0`` regardless of content; a taller or
  wider prediction is penalised for its extra (unmatched) cells.
* **content_accuracy** — of the *gold* cells, the fraction whose normalized text
  matches the prediction at the same ``(row, col)``. Empty gold scores ``0.0``
  (nothing to be right about).

Cells are compared at aligned ``(row, col)`` positions up to the per-axis
minimum shape (:func:`grid_align`), after :func:`normalize_cell` folding
(strip + whitespace-collapse + casefold). Pure Python, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")


def normalize_cell(s: str) -> str:
    """Fold a cell for comparison — strip, collapse whitespace, casefold (§23.34).

    ``' Fe  0.5 '`` → ``'fe 0.5'``. Casefolding makes the match case-insensitive
    так же, как OmniDocBench normalises cell text before TEDS scoring.
    """
    return _WS.sub(" ", str(s).strip()).casefold()


@dataclass(frozen=True)
class TableScore:
    """Frozen verdict of a table-structure comparison — вердикт таблицы (§23.34).

    * ``n_gold_cells`` / ``n_pred_cells`` — total cell counts of each table;
    * ``shape_match`` — the two tables have identical row/column dimensions;
    * ``cell_content_matches`` — aligned positions whose normalized text is equal;
    * ``structure_similarity`` — matched positions / ``max(gold, pred)`` cells;
    * ``content_accuracy`` — ``cell_content_matches`` / ``n_gold_cells`` (0.0 on
      empty gold).
    """

    n_gold_cells: int
    n_pred_cells: int
    shape_match: bool
    cell_content_matches: int
    structure_similarity: float
    content_accuracy: float

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view with stable keys (§23.34)."""
        return {
            "n_gold_cells": self.n_gold_cells,
            "n_pred_cells": self.n_pred_cells,
            "shape_match": self.shape_match,
            "cell_content_matches": self.cell_content_matches,
            "structure_similarity": self.structure_similarity,
            "content_accuracy": self.content_accuracy,
        }


def _cell_count(table: list[list[str]]) -> int:
    """Total number of cells across all rows — общее число ячеек."""
    return sum(len(row) for row in table)


def grid_align(gold: list[list[str]], pred: list[list[str]]) -> TableScore:
    """Score ``pred`` against ``gold`` by aligned-grid comparison (§23.34/§23.31).

    Cells are compared at aligned ``(row, col)`` positions up to the min shape
    per axis. ``structure_similarity`` is the count of positions present in *both*
    grids divided by ``max(gold_cells, pred_cells)``; ``content_accuracy`` is the
    number of aligned positions whose :func:`normalize_cell` text is equal divided
    by ``n_gold_cells`` (``0.0`` when gold is empty). Two empty tables are treated
    as perfectly aligned (``structure_similarity == 1.0``).
    """
    n_gold = _cell_count(gold)
    n_pred = _cell_count(pred)

    matched_positions = 0
    content_matches = 0
    for g_row, p_row in zip(gold, pred, strict=False):
        for g_cell, p_cell in zip(g_row, p_row, strict=False):
            matched_positions += 1
            if normalize_cell(g_cell) == normalize_cell(p_cell):
                content_matches += 1

    largest = max(n_gold, n_pred)
    structure_similarity = 1.0 if largest == 0 else matched_positions / largest

    shape_match = [len(r) for r in gold] == [len(r) for r in pred]

    content_accuracy = 0.0 if n_gold == 0 else content_matches / n_gold

    return TableScore(
        n_gold_cells=n_gold,
        n_pred_cells=n_pred,
        shape_match=shape_match,
        cell_content_matches=content_matches,
        structure_similarity=structure_similarity,
        content_accuracy=content_accuracy,
    )
