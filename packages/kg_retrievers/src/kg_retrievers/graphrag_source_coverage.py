"""GraphRAG source-coverage aggregation (§11.11).

When GraphRAG produces several community reports (отчёты по кластерам), each
report cites a set of source documents (документы-источники). To audit *how
broadly* an answer draws on the corpus, this module aggregates the cited
document ids across a batch of reports:

- ``doc_ids`` — the union of all cited documents, sorted ascending;
- ``per_doc_reports`` — how many reports cite each document;
- ``coverage_ratio`` — ``n_docs / n_reports`` (breadth per report), ``0`` when
  there are no reports.

Deterministic and offline-safe (no LLM); complements the per-community citation
tracing in :mod:`kg_retrievers.graphrag_citations` (§11.11).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceCoverage:
    """Aggregate document coverage across GraphRAG reports (§11.11).

    Attributes:
        doc_ids: union of all cited document ids (документы), sorted ascending.
        per_doc_reports: for each document, how many reports cite it.
        n_reports: number of aggregated reports (отчёты).
        n_docs: number of distinct cited documents (== ``len(doc_ids)``).
        coverage_ratio: ``n_docs / n_reports`` — breadth per report; ``0.0``
            when ``n_reports`` is zero.
    """

    doc_ids: tuple[str, ...]
    per_doc_reports: dict[str, int]
    n_reports: int
    n_docs: int
    coverage_ratio: float

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (copies the containers)."""
        return {
            "doc_ids": list(self.doc_ids),
            "per_doc_reports": dict(self.per_doc_reports),
            "n_reports": self.n_reports,
            "n_docs": self.n_docs,
            "coverage_ratio": self.coverage_ratio,
        }


def aggregate_sources(
    reports: list[dict],
    *,
    doc_key: str = "doc_ids",
) -> SourceCoverage:
    """Aggregate cited document ids across GraphRAG reports (§11.11).

    Collects the union of cited document ids (documents read from ``doc_key`` of
    each report), counts how many reports cite each document, and computes
    ``coverage_ratio == n_docs / n_reports`` (``0.0`` when there are no reports).

    A report whose ``doc_key`` is missing or empty contributes nothing. Within a
    single report a document is counted at most once (duplicates collapse).
    """
    counts: Counter[str] = Counter()
    for report in reports:
        raw = report.get(doc_key) or []
        # Dedup within a report so per_doc_reports counts *reports*, not mentions.
        for doc in {str(d) for d in raw if d}:
            counts[doc] += 1

    doc_ids = tuple(sorted(counts))
    n_reports = len(reports)
    n_docs = len(doc_ids)
    coverage_ratio = (n_docs / n_reports) if n_reports else 0.0
    return SourceCoverage(
        doc_ids=doc_ids,
        per_doc_reports=dict(counts),
        n_reports=n_reports,
        n_docs=n_docs,
        coverage_ratio=coverage_ratio,
    )


def top_cited(cov: SourceCoverage, k: int) -> list[tuple[str, int]]:
    """Return the ``k`` most-cited documents as ``(doc_id, count)``, desc (§11.11).

    Ties are broken by ascending document id for a deterministic order. A
    non-positive ``k`` yields an empty list.
    """
    if k <= 0:
        return []
    ranked = sorted(cov.per_doc_reports.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:k]
