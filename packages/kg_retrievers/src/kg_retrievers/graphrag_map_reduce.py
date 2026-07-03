"""GraphRAG map-reduce reduce step for global search (§11.7).

GraphRAG global search (глобальный поиск) answers a thematic question by *mapping*
it over community reports (отчёты по сообществам) — each map task yields a partial
answer scored by ``relevance`` (релевантность) — and then *reducing* those partials
into one consolidated answer.

This module implements the deterministic, offline-safe **reduce** step. Given the
map partials (каждый partial: ``{community_id, relevance, findings, doc_ids}``) it:

- drops partials whose ``relevance`` is below ``min_relevance`` (counting them in
  ``dropped``);
- orders the survivors by ``relevance`` descending (stable on ties);
- deduplicates findings (наблюдения) preserving first-seen order, capped at
  ``max_findings``;
- unions the survivors' source-document ids (документы-источники), sorted.

No LLM and no graph store are involved: pure aggregation over the map output,
complementing the community search in :mod:`kg_retrievers.community_search` (§11.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReducedAnswer:
    """Consolidated GraphRAG global-search answer after the reduce step (§11.7).

    Attributes:
        used_community_ids: community ids (сообщества) of the surviving partials,
            ordered by relevance descending (matching the reduce ordering).
        findings: deduplicated findings (наблюдения) in first-seen order, capped at
            ``max_findings``.
        cited_doc_ids: sorted union of the survivors' source-document ids.
        dropped: number of partials discarded for being below ``min_relevance``.
    """

    used_community_ids: tuple[int, ...]
    findings: tuple[str, ...]
    cited_doc_ids: tuple[str, ...]
    dropped: int

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (tuples become lists)."""
        return {
            "used_community_ids": list(self.used_community_ids),
            "findings": list(self.findings),
            "cited_doc_ids": list(self.cited_doc_ids),
            "dropped": self.dropped,
        }


def select_partials(partials: list[dict], min_relevance: float) -> list[dict]:
    """Return partials at/above ``min_relevance``, ordered by relevance descending.

    The sort is stable, so partials with equal relevance keep their input order
    (детерминированность). Missing ``relevance`` is treated as ``0.0``.
    """
    survivors = [p for p in partials if float(p.get("relevance", 0.0)) >= min_relevance]
    survivors.sort(key=lambda p: float(p.get("relevance", 0.0)), reverse=True)
    return survivors


def reduce_partials(
    partials: list[dict],
    *,
    min_relevance: float = 0.1,
    max_findings: int = 20,
) -> ReducedAnswer:
    """Reduce map partials into one consolidated answer (§11.7).

    Each partial is ``{community_id, relevance, findings: list[str], doc_ids:
    list[str]}``. Partials below ``min_relevance`` are dropped (and counted in
    ``dropped``); survivors are ordered by relevance descending. Findings are
    deduplicated preserving first-seen order across the ordered survivors and
    capped at ``max_findings``; document ids are unioned and sorted.
    """
    survivors = select_partials(partials, min_relevance)
    dropped = len(partials) - len(survivors)

    used_ids: list[int] = [int(p["community_id"]) for p in survivors]

    findings: list[str] = []
    seen: set[str] = set()
    for p in survivors:
        for f in p.get("findings", []):
            if f in seen:
                continue
            seen.add(f)
            findings.append(f)
            if len(findings) >= max_findings:
                break
        if len(findings) >= max_findings:
            break

    docs: set[str] = set()
    for p in survivors:
        docs.update(d for d in p.get("doc_ids", []) if d)

    return ReducedAnswer(
        used_community_ids=tuple(used_ids),
        findings=tuple(findings),
        cited_doc_ids=tuple(sorted(docs)),
        dropped=dropped,
    )
