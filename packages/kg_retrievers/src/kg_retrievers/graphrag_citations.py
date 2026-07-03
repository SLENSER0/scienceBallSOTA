"""GraphRAG citation & evidence traceability (§11.11).

When GraphRAG answers a thematic question from a *community* (кластер знаний), the
answer must remain auditable: every claim should trace back to the supporting
Evidence (эвиденс) and the source documents (документы-источники) behind the
community's member entities.

This module walks the ``SUPPORTED_BY`` provenance edges of a community's members
over a :class:`~kg_retrievers.graph_store.KuzuGraphStore` and collects, with
deduplication:

- ``evidence_ids`` — Evidence nodes cited either directly (edge target) or via the
  edge's ``evidence_ids`` property;
- ``doc_ids`` — the source documents (``doc_id``) of those Evidence nodes;
- ``cited_entities`` — the subset of members that actually carry provenance.

Deterministic and offline-safe (no LLM); complements the GraphRAG community search
in :mod:`kg_retrievers.community_search` (§11.7) with citations (§11.11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

if TYPE_CHECKING:  # avoid a runtime import cycle; used for type hints only
    from kg_retrievers.community_search import CommunityHit

_log = get_logger("graphrag_citations")

# Provenance relation linking a factual/entity node to its source (§3.6).
_SUPPORTED_BY = "SUPPORTED_BY"
_EVIDENCE_LABEL = "Evidence"


@dataclass(frozen=True)
class CommunitySources:
    """Auditable citations behind a GraphRAG community answer (§11.11).

    Attributes:
        community_id: id of the community (кластер) these sources back, or ``-1``
            when tracing an ad-hoc set of members without a community.
        doc_ids: deduplicated source-document ids (документы), sorted.
        evidence_ids: deduplicated Evidence node ids (эвиденс), sorted.
        cited_entities: members that carry provenance — a subset of the input
            member ids, sorted.
    """

    community_id: int
    doc_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    cited_entities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (copies the lists)."""
        return {
            "community_id": self.community_id,
            "doc_ids": list(self.doc_ids),
            "evidence_ids": list(self.evidence_ids),
            "cited_entities": list(self.cited_entities),
        }


def _parse_ids(raw: Any) -> list[str]:
    """Parse an edge ``evidence_ids`` value (JSON string / list / None) into ids."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return [raw]
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
        return [str(parsed)] if parsed else []
    return []


def _member_supports(store: KuzuGraphStore, member_id: str) -> tuple[set[str], set[str]]:
    """Return ``(evidence_ids, doc_ids)`` traced from one member's SUPPORTED_BY edges.

    An Evidence node may be the direct edge target, or referenced by the edge's
    ``evidence_ids`` property (when the target is a Paper/документ). Both are
    collected; document ids are read directly only when the target is Evidence.
    """
    rows = store.rows(
        "MATCH (m:Node {id:$id})-[r:Rel]->(t:Node) WHERE r.type=$rt "
        "RETURN t.id, t.label, t.doc_id, r.evidence_ids",
        {"id": member_id, "rt": _SUPPORTED_BY},
    )
    ev_ids: set[str] = set()
    doc_ids: set[str] = set()
    for t_id, t_label, t_doc, edge_eids in rows:
        if t_label == _EVIDENCE_LABEL and t_id:
            ev_ids.add(t_id)
            if t_doc:
                doc_ids.add(t_doc)
        for eid in _parse_ids(edge_eids):
            ev_ids.add(eid)
    return ev_ids, doc_ids


def _docs_for_evidence(store: KuzuGraphStore, ev_ids: set[str]) -> set[str]:
    """Resolve the source-document ids (``doc_id``) of the given Evidence nodes."""
    if not ev_ids:
        return set()
    rows = store.rows(
        "MATCH (e:Node) WHERE e.id IN $ids AND e.doc_id IS NOT NULL RETURN DISTINCT e.doc_id",
        {"ids": list(ev_ids)},
    )
    return {r[0] for r in rows if r[0]}


def trace_answer_sources(
    store: KuzuGraphStore,
    member_ids: list[str],
    *,
    community_id: int = -1,
) -> CommunitySources:
    """Aggregate the citations backing a community answer across its members (§11.11).

    Walks each member's ``SUPPORTED_BY`` provenance, dedups Evidence and document
    ids across the whole community, and records which members were actually cited.
    Unknown/duplicate member ids are skipped gracefully; an empty ``member_ids``
    yields an empty :class:`CommunitySources`.
    """
    all_ev: set[str] = set()
    all_doc: set[str] = set()
    cited: list[str] = []
    seen: set[str] = set()
    for mid in member_ids:
        if not mid or mid in seen:
            continue
        seen.add(mid)
        ev, doc = _member_supports(store, mid)
        if not ev and not doc:
            continue
        all_ev |= ev
        all_doc |= doc
        cited.append(mid)
    all_doc |= _docs_for_evidence(store, all_ev)
    return CommunitySources(
        community_id=community_id,
        doc_ids=sorted(all_doc),
        evidence_ids=sorted(all_ev),
        cited_entities=sorted(cited),
    )


def trace_community_hit(store: KuzuGraphStore, hit: CommunityHit) -> CommunitySources:
    """Trace sources for a :class:`CommunityHit` from ``community_search.global_search``.

    Convenience wrapper carrying the hit's ``community_id`` into the result (§11.11).
    """
    return trace_answer_sources(store, hit.member_ids, community_id=hit.community_id)
