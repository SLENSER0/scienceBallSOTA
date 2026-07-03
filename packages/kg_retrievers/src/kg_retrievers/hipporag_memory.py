"""HippoRAG-2 Personalized-PageRank memory retrieval (§12.5).

Память по персонализированному PageRank / PPR memory retrieval, after HippoRAG 2
(Gutiérrez et al., "From RAG to Memory: Non-Parametric Continual Learning for
LLMs", arXiv:2502.14802, OSU-NLP Group, MIT license —
https://arxiv.org/abs/2502.14802,
https://github.com/OSU-NLP-Group/HippoRAG).

HippoRAG models long-term memory as a knowledge graph — the "synaptic index". The
entities a query recognises become *seed* nodes, and a single Personalized PageRank
pass (restart mass placed on those seeds) spreads activation across the graph, so
multi-hop-associated entities surface even when no single edge links them to a seed.
We rank every entity by its PPR score and, for the top-k, gather the source documents
that support them by walking ``(entity)-[:SUPPORTED_BY]->(Evidence)`` and reading each
Evidence's ``doc_id``.

This module builds strictly on
:func:`kg_retrievers.graph_pagerank.personalized_pagerank` (reused, never modified).
Following the Kuzu modelling rule, Cypher ``RETURN``s only base columns (``id`` /
``label``); the ``doc_id`` join-key prop is read per-Evidence via
:meth:`KuzuGraphStore.get_node`, not selected as a column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_pagerank import personalized_pagerank
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("hipporag_memory")

# Provenance edge/label linking an entity to its source document (§3.6 / §25.15).
SUPPORTED_BY_TYPE = "SUPPORTED_BY"
EVIDENCE_LABEL = "Evidence"


@dataclass(frozen=True)
class MemoryResult:
    """Result of one HippoRAG PPR memory retrieval (§12.5).

    Attributes:
        seeds: узлы-затравки / seed entity ids the PPR restart mass sat on (echoed
            back verbatim, including ids absent from the graph).
        ranked: сущности по убыванию PPR-оценки / entities ranked by descending PPR
            score, each ``{"id": <entity id>, "score": <float>}``, capped to ``top_k``.
        doc_ids: документы-источники / distinct source-document ids supporting the
            top-k entities via ``SUPPORTED_BY``→Evidence, sorted.
    """

    seeds: list[str]
    ranked: list[dict[str, Any]]
    doc_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (deep-copies the id lists)."""
        return {
            "seeds": list(self.seeds),
            "ranked": [{"id": r["id"], "score": r["score"]} for r in self.ranked],
            "doc_ids": list(self.doc_ids),
        }


def _supporting_doc_ids(store: KuzuGraphStore, entity_ids: list[str]) -> list[str]:
    """Distinct source ``doc_id``s supporting ``entity_ids`` via SUPPORTED_BY (§3.6).

    Walks ``(entity)-[:SUPPORTED_BY]->(Evidence)`` (RETURN base column ``id`` only) and
    reads each Evidence's ``doc_id`` join-key prop via ``get_node`` — an Evidence with
    no ``doc_id`` simply contributes nothing rather than raising.
    """
    if not entity_ids:
        return []
    ev_rows = store.rows(
        "MATCH (n:Node)-[r:Rel]->(e:Node) "
        "WHERE n.id IN $ids AND r.type=$sb AND e.label=$ev RETURN DISTINCT e.id",
        {"ids": entity_ids, "sb": SUPPORTED_BY_TYPE, "ev": EVIDENCE_LABEL},
    )
    doc_ids: set[str] = set()
    for row in ev_rows:
        e_id = row[0]
        if not e_id:
            continue
        ev = store.get_node(e_id)
        if ev and ev.get("doc_id"):
            doc_ids.add(ev["doc_id"])
    return sorted(doc_ids)


def hipporag_retrieve(
    store: KuzuGraphStore,
    seed_entities: list[str],
    *,
    top_k: int = 10,
) -> MemoryResult:
    """Retrieve memory by Personalized PageRank over the synaptic index (§12.5).

    Places PPR restart mass on ``seed_entities``, ranks every entity by its resulting
    PPR score (descending, ties by id — inherited from
    :func:`personalized_pagerank`), keeps the top ``top_k``, and gathers the source
    documents that support those top-k entities via ``SUPPORTED_BY``→Evidence.

    Degrades gracefully: seeds absent from the graph fall back to a uniform restart
    (plain PageRank) inside :func:`personalized_pagerank`, and an empty graph yields an
    empty ranking and no ``doc_ids`` — never an error.
    """
    scored = personalized_pagerank(store, list(seed_entities), top=top_k)
    ranked = [{"id": s.entity_id, "score": s.score} for s in scored]
    doc_ids = _supporting_doc_ids(store, [r["id"] for r in ranked])
    _log.info(
        "hipporag.retrieve",
        seeds=len(seed_entities),
        ranked=len(ranked),
        docs=len(doc_ids),
    )
    return MemoryResult(seeds=list(seed_entities), ranked=ranked, doc_ids=doc_ids)
