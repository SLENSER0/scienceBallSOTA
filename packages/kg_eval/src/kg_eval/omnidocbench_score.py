"""OmniDocBench end-to-end document-parse scoring — сквозная оценка парсинга.

Deterministic, hand-checkable end-to-end scoring of a document *prediction*
against a *gold* reference in the spirit of **OmniDocBench** — the multi-source,
multi-level benchmark for real-world document parsing (Ouyang et al., CVPR 2025,
arXiv:2412.07626, OpenDataLab: https://github.com/opendatalab/OmniDocBench).
OmniDocBench grades a parser across heterogeneous page components — running
text, tables and formulas — using normalized edit distance for text/formulas and
TEDS for tables; this module composes those per-component facets into a single
weighted document score (§23.34/§23.31).

Each :class:`ParsedDoc` carries three parsed components:

* **text** — free-running prose, scored by normalized character edit distance
  (reused from :mod:`kg_eval.text_edit_distance`); ``text_score`` is the
  ``similarity`` facet ``1 - edits / max(len)`` and ``edit_distance`` is its
  complement ``edits / max(len)`` in ``[0, 1]``;
* **table** — a list-of-rows cell grid, scored by the TEDS-lite metric of
  :mod:`kg_eval.table_teds`; ``table_score`` is the mean of that metric's
  ``structure_similarity`` and ``content_accuracy`` facets (both-absent tables
  score ``1.0`` — nothing to get wrong);
* **formula** — a single formula string, scored by whitespace-insensitive exact
  match (``1.0``/``0.0``), mirroring OmniDocBench's strict formula acceptance.

:func:`omnidoc_score` folds the three into ``overall`` with the fixed OmniDocBench
component weights — text ``0.5``, table ``0.3``, formula ``0.2``. Pure Python, no
I/O; builds on the two sibling scorers and edits neither.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kg_eval.table_teds import grid_align
from kg_eval.text_edit_distance import score as text_score_report

# Fixed OmniDocBench component weights (text-dominant, formula least) — веса.
TEXT_WEIGHT = 0.5
TABLE_WEIGHT = 0.3
FORMULA_WEIGHT = 0.2

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedDoc:
    """One parsed document — text, a table grid and a formula (§23.34).

    All three components default to empty so a fixture can populate only the
    facets it exercises. ``table`` is a list-of-rows of cell strings (the shape
    :func:`kg_eval.table_teds.grid_align` expects); ``formula`` is a single
    formula string compared by whitespace-insensitive exact match.
    """

    text: str = ""
    table: list[list[str]] = field(default_factory=list)
    formula: str = ""


@dataclass(frozen=True)
class OmniDocScore:
    """Frozen OmniDocBench verdict for one document — вердикт документа (§23.34).

    * ``text_score`` — text edit-distance ``similarity`` in ``[0, 1]``;
    * ``table_score`` — TEDS-lite table score in ``[0, 1]`` (``1.0`` when both
      documents have no table);
    * ``formula_score`` — ``1.0`` on whitespace-insensitive exact formula match,
      else ``0.0``;
    * ``overall`` — the weighted blend ``0.5·text + 0.3·table + 0.2·formula``;
    * ``edit_distance`` — the text normalized edit distance ``1 - text_score``.
    """

    text_score: float
    table_score: float
    formula_score: float
    overall: float
    edit_distance: float

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view with stable keys (§23.34)."""
        return {
            "text_score": self.text_score,
            "table_score": self.table_score,
            "formula_score": self.formula_score,
            "overall": self.overall,
            "edit_distance": self.edit_distance,
        }


def _normalize_formula(s: str) -> str:
    """Fold a formula for exact match — strip + collapse whitespace (§23.34).

    Whitespace is normalised (``'E = m c^2'`` → ``'E = m c^2'`` collapses runs)
    but case is preserved, since formula variables are case-sensitive unlike the
    casefolded table cells of :func:`kg_eval.table_teds.normalize_cell`.
    """
    return _WS.sub(" ", str(s).strip())


def _table_teds(gold: list[list[str]], pred: list[list[str]]) -> float:
    """TEDS-lite scalar for one table pair — единый балл таблицы (§23.34/§23.31).

    Mean of the ``structure_similarity`` and ``content_accuracy`` facets from
    :func:`kg_eval.table_teds.grid_align`. When *both* tables are absent there is
    nothing to score, so the pair is treated as a perfect match (``1.0``); a
    present gold with an empty prediction (or vice versa) scores below ``1.0``.
    """
    ts = grid_align(gold, pred)
    if ts.n_gold_cells == 0 and ts.n_pred_cells == 0:
        return 1.0
    return (ts.structure_similarity + ts.content_accuracy) / 2.0


def _formula_score(gold: str, pred: str) -> float:
    """Exact-match formula score — ``1.0`` iff normalized strings agree (§23.34).

    Two empty formulas normalise to ``''`` and therefore match (``1.0``); a
    non-empty gold with a differing prediction scores ``0.0``.
    """
    return 1.0 if _normalize_formula(gold) == _normalize_formula(pred) else 0.0


def omnidoc_score(gold: ParsedDoc, pred: ParsedDoc) -> OmniDocScore:
    """Score *pred* against *gold* end-to-end into an :class:`OmniDocScore`.

    Combines text normalized edit distance, TEDS-lite table similarity and
    exact-match formula scoring into a weighted ``overall`` using the fixed
    OmniDocBench weights (text ``0.5`` / table ``0.3`` / formula ``0.2``). An
    identical document scores ``overall == 1.0``; two empty documents also score
    ``1.0`` (every component is a vacuous match) — arXiv:2412.07626, §23.34.
    """
    text_report = text_score_report(gold.text, pred.text)
    text = text_report.similarity
    table = _table_teds(gold.table, pred.table)
    formula = _formula_score(gold.formula, pred.formula)

    overall = TEXT_WEIGHT * text + TABLE_WEIGHT * table + FORMULA_WEIGHT * formula
    return OmniDocScore(
        text_score=text,
        table_score=table,
        formula_score=formula,
        overall=overall,
        edit_distance=1.0 - text,
    )
