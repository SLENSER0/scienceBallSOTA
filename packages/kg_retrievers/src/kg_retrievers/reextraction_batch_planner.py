"""§25.8 Re-extraction batch planner: group near-miss cells by source doc, rank by yield.

RU: Планировщик пакетной ре-экстракции (§25.8). Ячейки-«почти-промахи» — словари
``{doc_id, p_extractor_missed, material, property}`` — группируются по исходному
документу; для каждого документа ожидаемое восстановление равно сумме
``p_extractor_missed`` его ячеек. Документы сортируются по убыванию ожидаемого
восстановления (ничьи — по ``doc_id`` лексикографически), чтобы куратор перезапускал
LLM-извлечение документ-за-документом, начиная с наивысшего ожидаемого выхода.
Возвращается неизменяемый :class:`ReextractionPlan` с накопительным восстановлением
``cumulative``. В отличие от ``gap_closure_plan`` (set-cover по экспериментам) и
``near_miss_gaps`` (плоское перечисление), здесь — порядок документов и их выход.
Чистый python: граф/стор не трогает.
EN: Re-extraction batch planner (§25.8). Near-miss ``cells`` — dicts
``{doc_id, p_extractor_missed, material, property}`` — are grouped by source document;
each document's expected recovery is the sum of its cells' ``p_extractor_missed``.
Documents sort by descending expected recovery (ties by ``doc_id`` lexicographically) so
a curator re-runs LLM extraction doc-by-doc, highest expected yield first. Returns an
immutable :class:`ReextractionPlan` carrying a non-decreasing ``cumulative`` recovery.
Distinct from ``gap_closure_plan`` (set-cover over experiments) and ``near_miss_gaps``
(flat enumeration): here it is document ordering and per-document yield. Pure python — it
touches no graph/store.

Kuzu note: custom node props are not queryable columns — a caller assembling ``cells``
from Kuzu must RETURN base columns and read ``p_extractor_missed``/``material`` via
``get_node()`` before building the plain dicts this module consumes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Round expected recoveries to tame float summation noise while staying hand-checkable.
_NDIGITS = 12


@dataclass(frozen=True)
class ReextractionBatch:
    """One document's re-extraction batch (§25.8).

    ``doc_id`` is the source document; ``n_cells`` the count of near-miss cells it holds;
    ``expected_recovered`` the summed ``p_extractor_missed`` over those cells (rounded).
    """

    doc_id: str
    n_cells: int
    expected_recovered: float

    def as_dict(self) -> dict:
        """Plain-dict projection for JSON dump / round-trip (§25.8, house style)."""
        return {
            "doc_id": self.doc_id,
            "n_cells": self.n_cells,
            "expected_recovered": self.expected_recovered,
        }


@dataclass(frozen=True)
class ReextractionPlan:
    """Immutable ranked re-extraction plan over documents (§25.8).

    ``batches`` are per-document batches sorted by descending ``expected_recovered`` then
    ``doc_id``; ``total_expected`` the summed expected recovery across all documents; and
    ``cumulative`` the running total of ``expected_recovered`` following ``batches`` order,
    a non-decreasing list whose last element equals ``total_expected``.
    """

    batches: list[ReextractionBatch]
    total_expected: float
    cumulative: list[float]

    def as_dict(self) -> dict:
        """Plain-dict projection for JSON dump / round-trip (§25.8, house style)."""
        return {
            "batches": [b.as_dict() for b in self.batches],
            "total_expected": self.total_expected,
            "cumulative": list(self.cumulative),
        }


def _cell_doc_and_p(cell: dict) -> tuple[str, float]:
    """Extract ``(doc_id, p_extractor_missed)`` from one near-miss cell (§25.8).

    ``doc_id`` is required; ``p_extractor_missed`` must be a probability in ``[0, 1]``.
    """
    if "doc_id" not in cell:
        raise ValueError(f"cell must contain 'doc_id', got {cell!r}")
    if "p_extractor_missed" not in cell:
        raise ValueError(f"cell must contain 'p_extractor_missed', got {cell!r}")
    doc_id = str(cell["doc_id"])
    p = float(cell["p_extractor_missed"])
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p_extractor_missed for {doc_id!r} must be in [0, 1], got {p!r}")
    return doc_id, p


def plan_reextraction(cells: list) -> ReextractionPlan:
    """Group near-miss ``cells`` by document and rank highest expected yield first (§25.8).

    Each cell is a ``{doc_id, p_extractor_missed, material, property}`` dict. Documents are
    grouped and each gets ``expected_recovered = sum(p_extractor_missed)`` over its cells.
    Batches sort by descending ``expected_recovered`` then ``doc_id`` (ascending). The
    returned plan carries ``total_expected`` (sum over all cells) and a non-decreasing
    ``cumulative`` running total whose last element equals ``total_expected``. Empty input
    yields no batches, ``total_expected == 0.0`` and an empty ``cumulative``.
    """
    n_cells: dict[str, int] = {}
    summed: dict[str, float] = {}
    for cell in cells:
        doc_id, p = _cell_doc_and_p(cell)
        n_cells[doc_id] = n_cells.get(doc_id, 0) + 1
        summed[doc_id] = summed.get(doc_id, 0.0) + p

    total_expected = round(sum(summed.values()), _NDIGITS)

    batches = [
        ReextractionBatch(
            doc_id=doc_id,
            n_cells=n_cells[doc_id],
            expected_recovered=round(summed[doc_id], _NDIGITS),
        )
        for doc_id in summed
    ]
    # Highest expected yield first; ties broken by doc_id ascending for determinism.
    batches.sort(key=lambda b: (-b.expected_recovered, b.doc_id))

    cumulative: list[float] = []
    running = 0.0
    for batch in batches:
        running = round(running + batch.expected_recovered, _NDIGITS)
        cumulative.append(running)

    return ReextractionPlan(
        batches=batches,
        total_expected=total_expected,
        cumulative=cumulative,
    )
