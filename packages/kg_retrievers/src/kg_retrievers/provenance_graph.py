"""Provenance-chain builder for a single fact / Measurement (§25.15).

Where :mod:`kg_retrievers.observation_lineage` rolls the provenance of an
observation up into deduplicated *sets* of ids, this module turns the same walk
into an *ordered chain* — the auditable trail (цепочка происхождения) a reviewer
reads from the fact back to its source document (§3.6/§3.7).

The ontology models the provenance of a ``Measurement`` (наблюдение / факт) as the
two-hop path

    (Measurement)-[:SUPPORTED_BY]->(Evidence)-[:FROM_CHUNK]->(Chunk)

plus two join keys carried as node props: the Evidence's ``doc_id`` (the source
document, документ-источник) and the Measurement's ``extractor_run_id`` (the
extraction run, прогон извлечения, that emitted the fact).

:func:`provenance_chain` walks that path over a :class:`KuzuGraphStore` and emits a
:class:`ProvenanceChain` whose ``chain`` field lists the provenance levels in the
fixed order ``measurement <- evidence <- chunk <- doc`` (fact first, source last).
A level is present only when it carries at least one id, so a missing ``FROM_CHUNK``
edge or a missing ``doc_id`` simply truncates the chain rather than raising.

The module is strictly read-only. Following the Kuzu modelling rule, Cypher only
``RETURN``s base columns (``id`` / ``label``); the join-key props (``doc_id``,
``extractor_run_id``) are read via :meth:`KuzuGraphStore.get_node`, because custom
props live in the JSON ``props`` catch-all and are not queryable columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("provenance_graph")

# Provenance edges/labels on Measurement→Evidence→Chunk (§25.15 / §3.6).
SUPPORTED_BY_TYPE = "SUPPORTED_BY"
FROM_CHUNK_TYPE = "FROM_CHUNK"
MEASUREMENT_LABEL = "Measurement"
EVIDENCE_LABEL = "Evidence"
CHUNK_LABEL = "Chunk"

# Provenance levels, ordered fact→source (цепочка: факт → документ-источник).
MEASUREMENT_KIND = "measurement"
EVIDENCE_KIND = "evidence"
CHUNK_KIND = "chunk"
DOC_KIND = "doc"


@dataclass(frozen=True)
class ProvenanceChain:
    """Ordered provenance chain behind one Measurement / fact (§25.15).

    Attributes:
        measurement_id: id of the observed ``Measurement`` (факт / наблюдение).
        evidence: distinct ``Evidence`` ids the measurement is SUPPORTED_BY, sorted
            (эвиденс).
        chunks: distinct ``Chunk`` ids reached via Evidence-FROM_CHUNK->Chunk,
            sorted (чанки).
        docs: distinct source-document ids (документы) — the Evidence ``doc_id`` —
            sorted.
        extractor_run: the extraction run (прогон) that produced the fact, or
            ``None`` when the measurement carries no run stamp.
        chain: the provenance levels in fixed order
            ``measurement <- evidence <- chunk <- doc``. Each entry is
            ``{"kind": <level>, "ids": [...]}``; a level is present only when it
            carries at least one id, so missing links truncate the chain.
    """

    measurement_id: str
    evidence: list[str]
    chunks: list[str]
    docs: list[str]
    extractor_run: str | None
    chain: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (deep-copies the id lists/chain)."""
        return {
            "measurement_id": self.measurement_id,
            "evidence": list(self.evidence),
            "chunks": list(self.chunks),
            "docs": list(self.docs),
            "extractor_run": self.extractor_run,
            "chain": [{"kind": step["kind"], "ids": list(step["ids"])} for step in self.chain],
        }


def provenance_chain(store: KuzuGraphStore, measurement_id: str) -> ProvenanceChain:
    """Build the ordered provenance chain behind a Measurement / fact (§25.15).

    Walks ``(Measurement)-[:SUPPORTED_BY]->(Evidence)-[:FROM_CHUNK]->(Chunk)`` and
    reads the two join-key props (``extractor_run_id`` on the Measurement, ``doc_id``
    on each Evidence) via :meth:`KuzuGraphStore.get_node`, since those props are not
    queryable columns. Each hop is deduplicated and sorted.

    The returned ``chain`` orders the provenance levels ``measurement <- evidence <-
    chunk <- doc`` (fact first, source document last). Missing links degrade
    gracefully: a level with no ids is dropped, so an Evidence with no ``FROM_CHUNK``
    edge or no ``doc_id`` truncates the chain, and an unknown / unlinked
    ``measurement_id`` yields empty id lists, a ``None`` run and an empty chain —
    never an error.
    """
    node = store.get_node(measurement_id)
    run_id = node.get("extractor_run_id") if node else None

    # Evidence directly SUPPORTED_BY the measurement (RETURN base column id only).
    ev_rows = store.rows(
        "MATCH (m:Node {id:$id})-[r:Rel]->(e:Node) "
        "WHERE r.type=$sb AND e.label=$ev RETURN DISTINCT e.id",
        {"id": measurement_id, "sb": SUPPORTED_BY_TYPE, "ev": EVIDENCE_LABEL},
    )
    evidence_ids = sorted({r[0] for r in ev_rows if r[0]})

    # doc_id is a join-key prop → read per Evidence via get_node, not via query.
    doc_ids: set[str] = set()
    for e_id in evidence_ids:
        ev = store.get_node(e_id)
        if ev and ev.get("doc_id"):
            doc_ids.add(ev["doc_id"])

    # Chunks reached from those Evidence via FROM_CHUNK (RETURN base column id).
    chunk_ids: set[str] = set()
    if evidence_ids:
        ch_rows = store.rows(
            "MATCH (e:Node)-[r:Rel]->(c:Node) "
            "WHERE e.id IN $ids AND r.type=$fc AND c.label=$cl RETURN DISTINCT c.id",
            {"ids": evidence_ids, "fc": FROM_CHUNK_TYPE, "cl": CHUNK_LABEL},
        )
        chunk_ids = {r[0] for r in ch_rows if r[0]}

    docs = sorted(doc_ids)
    chunks = sorted(chunk_ids)

    # Ordered chain measurement <- evidence <- chunk <- doc; drop empty levels so
    # a missing link truncates rather than leaving a hollow step (§3.6 audit trail).
    chain: list[dict[str, Any]] = []
    if node is not None:
        chain.append({"kind": MEASUREMENT_KIND, "ids": [measurement_id]})
        for kind, ids in (
            (EVIDENCE_KIND, evidence_ids),
            (CHUNK_KIND, chunks),
            (DOC_KIND, docs),
        ):
            if ids:
                chain.append({"kind": kind, "ids": list(ids)})

    _log.info(
        "provenance_chain.built",
        measurement_id=measurement_id,
        levels=len(chain),
        n_evidence=len(evidence_ids),
    )
    return ProvenanceChain(
        measurement_id=measurement_id,
        evidence=evidence_ids,
        chunks=chunks,
        docs=docs,
        extractor_run=run_id,
        chain=chain,
    )
