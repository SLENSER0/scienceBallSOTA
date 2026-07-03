"""Observation provenance-lineage over the extraction-run join keys (§25.3).

An *observation* (наблюдение) is a ``Measurement`` that quantifies a property. To
stay auditable (§3.6/§3.7) each observation must trace back to the text it was read
from and to the extraction run (прогон извлечения) that produced it. The ontology
models this provenance as the two-hop path

    (Measurement)-[:SUPPORTED_BY]->(Evidence)-[:FROM_CHUNK]->(Chunk)

plus two join keys carried as node props: the Evidence's ``doc_id`` (the source
document, документ-источник) and the Measurement's ``extractor_run_id`` (the run
that emitted it).

This module walks that path over a :class:`KuzuGraphStore` and rolls it up:

- :func:`observation_lineage` — the full :class:`ObservationLineage` behind one
  measurement (run id + evidence + chunks + documents);
- :func:`observations_by_run` — the inverse grouping: the measurements a given
  ``extractor_run_id`` produced.

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

_log = get_logger("observation_lineage")

# Provenance edges on the path Measurement→Evidence→Chunk (§25.3 / §3.6).
SUPPORTED_BY_TYPE = "SUPPORTED_BY"
FROM_CHUNK_TYPE = "FROM_CHUNK"
MEASUREMENT_LABEL = "Measurement"
EVIDENCE_LABEL = "Evidence"
CHUNK_LABEL = "Chunk"


@dataclass(frozen=True)
class ObservationLineage:
    """Full provenance lineage of one observation / Measurement (§25.3).

    Attributes:
        measurement_id: id of the observed ``Measurement`` (наблюдение).
        extractor_run_id: the extraction run (прогон) that produced it, or ``None``
            when the measurement carries no run stamp.
        evidence_ids: distinct ``Evidence`` ids the measurement is SUPPORTED_BY,
            sorted (эвиденс).
        doc_ids: distinct source-document ids (документы) — the ``doc_id`` of that
            Evidence — sorted.
        chunk_ids: distinct ``Chunk`` ids reached via Evidence-FROM_CHUNK->Chunk,
            sorted (чанки).
    """

    measurement_id: str
    extractor_run_id: str | None
    evidence_ids: list[str]
    doc_ids: list[str]
    chunk_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (copies the id lists)."""
        return {
            "measurement_id": self.measurement_id,
            "extractor_run_id": self.extractor_run_id,
            "evidence_ids": list(self.evidence_ids),
            "doc_ids": list(self.doc_ids),
            "chunk_ids": list(self.chunk_ids),
        }


def observation_lineage(store: KuzuGraphStore, measurement_id: str) -> ObservationLineage:
    """Trace the full provenance lineage behind a Measurement observation (§25.3).

    Walks ``(Measurement)-[:SUPPORTED_BY]->(Evidence)-[:FROM_CHUNK]->(Chunk)`` and
    reads the two join-key props (``doc_id`` on Evidence, ``extractor_run_id`` on
    the Measurement) via :meth:`KuzuGraphStore.get_node`, since those props are not
    queryable columns. Each hop is deduplicated and sorted.

    Missing links degrade gracefully: an Evidence with no ``FROM_CHUNK`` edge or no
    ``doc_id`` simply contributes nothing to ``chunk_ids`` / ``doc_ids``, and an
    unknown / unlinked ``measurement_id`` yields empty id lists with a ``None`` run
    id — never an error.
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

    return ObservationLineage(
        measurement_id=measurement_id,
        extractor_run_id=run_id,
        evidence_ids=evidence_ids,
        doc_ids=sorted(doc_ids),
        chunk_ids=sorted(chunk_ids),
    )


def observations_by_run(store: KuzuGraphStore, run_id: str) -> list[str]:
    """Ids of the Measurements produced by extraction run ``run_id`` (§25.3).

    The inverse of :func:`observation_lineage`: it groups observations by their
    ``extractor_run_id`` join key. Every ``Measurement`` node is enumerated by its
    queryable ``label`` column, and each node's ``extractor_run_id`` is read via
    :meth:`KuzuGraphStore.get_node` (a prop, not a query column); the ids whose run
    stamp equals ``run_id`` are returned, sorted. An unknown ``run_id`` — or a run
    that stamped no measurement — yields ``[]``.
    """
    rows = store.rows(
        "MATCH (m:Node) WHERE m.label=$ml RETURN m.id",
        {"ml": MEASUREMENT_LABEL},
    )
    matched: list[str] = []
    for row in rows:
        m_id = row[0]
        if not m_id:
            continue
        node = store.get_node(m_id)
        if node and node.get("extractor_run_id") == run_id:
            matched.append(m_id)
    matched.sort()
    _log.info("observations_by_run.grouped", run_id=run_id, n=len(matched))
    return matched
