"""OmniDocBench end-to-end document-parse aggregator — сводный балл (§23.34/§23.31).

Where :mod:`text_edit_distance` and :mod:`table_teds` grade a *single* facet of a
parsed document, OmniDocBench reports one **end-to-end** number per document that
folds several already-computed per-facet subscores together, then breaks the
corpus down by document type. This module is that aggregator — агрегатор фасетов.

Each input document is a Mapping carrying a ``'doc_type'`` label plus any of the
four facet subscores, each already normalized to ``[0, 1]``:

* ``'text'`` — text-similarity (e.g. ``1 - CER``);
* ``'table'`` — table-structure TEDS;
* ``'formula'`` — formula-recognition similarity;
* ``'layout'`` — reading-order / layout agreement.

A facet key that is simply *absent* is skipped — it drops out of the denominator
rather than counting as a zero, so a document with no formulas is not punished for
lacking a formula score. :func:`score_documents` averages the *present* facets per
document (optionally weighted), takes the corpus overall as the mean of the
per-document overalls, and reports the mean overall per ``doc_type`` together with
the single worst-scoring type (ties broken alphabetically). Pure Python, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

FACETS: tuple[str, ...] = ("text", "table", "formula", "layout")
"""Recognised facet keys — распознаваемые фасеты (§23.34)."""


@dataclass(frozen=True)
class DocScore:
    """Frozen per-document verdict — вердикт по документу (§23.34).

    * ``doc_type`` — the document's declared type label;
    * ``overall`` — weighted mean of the facet subscores *present* on the document;
    * ``facets`` — the present facet subscores that fed ``overall`` (absent facets
      omitted entirely, never zero-filled).
    """

    doc_type: str
    overall: float
    facets: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view with stable keys (§23.34)."""
        return {
            "doc_type": self.doc_type,
            "overall": self.overall,
            "facets": dict(self.facets),
        }


@dataclass(frozen=True)
class OmniDocReport:
    """Frozen corpus-level end-to-end verdict — сводный отчёт (§23.34/§23.31).

    * ``n`` — number of scored documents;
    * ``overall`` — mean of the per-document overalls;
    * ``by_type`` — mean per-document overall grouped by ``doc_type``;
    * ``worst_type`` — the ``doc_type`` with the lowest mean overall (on a tie, the
      alphabetically first type).
    """

    n: int
    overall: float
    by_type: dict[str, float]
    worst_type: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view; ``by_type`` is emitted in sorted key order (§23.34)."""
        return {
            "n": self.n,
            "overall": self.overall,
            "by_type": {k: self.by_type[k] for k in sorted(self.by_type)},
            "worst_type": self.worst_type,
        }


def _doc_overall(
    doc: Mapping[str, object], weights: Mapping[str, float]
) -> tuple[float, dict[str, float]]:
    """Weighted mean of the present facet subscores of one document — (§23.34).

    Iterates :data:`FACETS` in order, keeping only the facets present as keys on
    *doc*; each contributes ``weight * value`` to the numerator and ``weight`` to
    the denominator. Returns ``(overall, present_facets)``. A document with no
    facet keys yields ``overall == 0.0`` and an empty facet dict.
    """
    present: dict[str, float] = {}
    numerator = 0.0
    denominator = 0.0
    for facet in FACETS:
        if facet not in doc:
            continue
        value = float(doc[facet])  # type: ignore[arg-type]
        weight = weights[facet]
        present[facet] = value
        numerator += weight * value
        denominator += weight
    overall = 0.0 if denominator == 0.0 else numerator / denominator
    return overall, present


def score_documents(
    docs: Sequence[Mapping[str, object]],
    *,
    weights: Mapping[str, float] | None = None,
) -> OmniDocReport:
    """Fold per-facet subscores into one end-to-end report — свернуть фасеты (§23.34/§23.31).

    *docs* is a sequence of Mappings, each with a ``'doc_type'`` label and any of
    the :data:`FACETS` subscores in ``[0, 1]``. Absent facets are skipped (excluded
    from the per-document denominator, not treated as ``0.0``). *weights* maps facet
    names to relative weights (default ``1.0`` each); a weight key outside
    :data:`FACETS` raises :class:`KeyError`. An empty *docs* raises
    :class:`ValueError`.

    The per-document overall is the weighted mean of its present facets; the corpus
    ``overall`` is the mean of those per-document overalls; ``by_type`` is the mean
    per-document overall grouped by ``doc_type``; ``worst_type`` is the type with
    the lowest mean overall (alphabetically first on a tie).
    """
    if not docs:
        raise ValueError("score_documents requires at least one document")

    resolved: dict[str, float] = dict.fromkeys(FACETS, 1.0)
    if weights is not None:
        for key, value in weights.items():
            if key not in resolved:
                raise KeyError(f"unknown weight key: {key!r}")
            resolved[key] = float(value)

    scores: list[DocScore] = []
    grouped: dict[str, list[float]] = {}
    for doc in docs:
        doc_type = str(doc["doc_type"])
        overall, facets = _doc_overall(doc, resolved)
        scores.append(DocScore(doc_type=doc_type, overall=overall, facets=facets))
        grouped.setdefault(doc_type, []).append(overall)

    overall = sum(s.overall for s in scores) / len(scores)
    by_type = {dt: sum(vals) / len(vals) for dt, vals in grouped.items()}

    # Lowest mean overall wins; ties broken by alphabetically-first type name.
    worst_type = min(by_type, key=lambda dt: (by_type[dt], dt))

    return OmniDocReport(
        n=len(scores),
        overall=overall,
        by_type=by_type,
        worst_type=worst_type,
    )
