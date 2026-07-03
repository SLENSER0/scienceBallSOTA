"""MENTIONS-lineage tracing for documents × entities (§25.7).

Distinct from *observations* (a ``Measurement`` that quantifies a property), a
*mention* (упоминание) is the weakest provenance link the corpus offers: a
``Chunk`` of a ``Document`` merely names an entity. The ontology models this as

    (Document)-[:HAS_CHUNK]->(Chunk)-[:MENTIONS]->(Entity)

This module traces that two-hop path in both directions over a
:class:`KuzuGraphStore` and rolls the pairs up into a serialisable matrix:

- :func:`documents_mentioning` — which документы name an entity;
- :func:`entities_mentioned_in` — which сущности a document names (the reverse);
- :func:`mention_matrix` — the aggregate ``MentionLineage`` over many entities;
- :func:`is_mentioned_without_observation` — the §25.11 *possible_miss* signal:
  a material is *mentioned* in some doc yet carries **no** ``Measurement`` of a
  property. Mentioned-but-never-measured is exactly where the extractor most
  plausibly missed a datum (наблюдение), as opposed to a true, real absence.

The module is strictly read-only: it never writes to the graph. All node reads
return base columns (``id`` / ``label`` / ``property_name`` …); the relationship
``type`` (``HAS_CHUNK`` / ``MENTIONS``) is filtered on ``r.type`` because custom
edge/node props live in the JSON ``props`` catch-all, not in queryable columns.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("mentions_lineage")

# Relationship types on the provenance path Document→Chunk→Entity (§25.7).
HAS_CHUNK_TYPE = "HAS_CHUNK"
MENTIONS_TYPE = "MENTIONS"

# How many hops out from a material a Measurement still counts as *observing* it
# (a Measurement typically attaches one hop away via ABOUT_MATERIAL/ABOUT_REGIME).
DEFAULT_OBSERVATION_DEPTH = 2


@dataclass(frozen=True)
class MentionLineage:
    """Aggregate MENTIONS lineage over a set of entities (§25.7).

    ``by_entity`` maps each queried ``entity_id`` to the sorted, distinct ids of
    the documents that mention it; ``n_mentions`` is the total number of distinct
    (entity, document) mention pairs across the whole matrix.
    """

    by_entity: dict[str, list[str]]
    n_mentions: int

    def as_dict(self) -> dict:
        return {
            "by_entity": {eid: list(docs) for eid, docs in self.by_entity.items()},
            "n_mentions": self.n_mentions,
        }


def documents_mentioning(store: KuzuGraphStore, entity_id: str) -> list[str]:
    """Ids of the documents that mention ``entity_id`` (§25.7).

    Traces ``(Document)-[:HAS_CHUNK]->(Chunk)-[:MENTIONS]->(entity)`` and returns
    the distinct ``Document`` ids, sorted. Unknown / unmentioned ids yield ``[]``.
    """
    rows = store.rows(
        "MATCH (d:Node)-[r1:Rel]->(c:Node)-[r2:Rel]->(e:Node {id:$eid}) "
        "WHERE d.label='Document' AND r1.type=$has AND c.label='Chunk' AND r2.type=$men "
        "RETURN DISTINCT d.id ORDER BY d.id",
        {"eid": entity_id, "has": HAS_CHUNK_TYPE, "men": MENTIONS_TYPE},
    )
    return [r[0] for r in rows]


def entities_mentioned_in(store: KuzuGraphStore, doc_id: str) -> list[str]:
    """Ids of the entities mentioned in document ``doc_id`` (§25.7, reverse trace).

    Traces ``(doc)-[:HAS_CHUNK]->(Chunk)-[:MENTIONS]->(Entity)`` and returns the
    distinct entity ids, sorted. Unknown doc ids yield ``[]``.
    """
    rows = store.rows(
        "MATCH (d:Node {id:$did})-[r1:Rel]->(c:Node)-[r2:Rel]->(e:Node) "
        "WHERE r1.type=$has AND c.label='Chunk' AND r2.type=$men "
        "RETURN DISTINCT e.id ORDER BY e.id",
        {"did": doc_id, "has": HAS_CHUNK_TYPE, "men": MENTIONS_TYPE},
    )
    return [r[0] for r in rows]


def mention_matrix(store: KuzuGraphStore, entity_ids: list[str]) -> MentionLineage:
    """Aggregate the MENTIONS lineage of many entities into a matrix (§25.7).

    Duplicate ``entity_ids`` are collapsed (order preserved). ``n_mentions`` sums
    the distinct documents per entity. An empty ``entity_ids`` yields an empty
    matrix (``by_entity == {}``, ``n_mentions == 0``).
    """
    by_entity: dict[str, list[str]] = {}
    n_mentions = 0
    for eid in dict.fromkeys(entity_ids):
        docs = documents_mentioning(store, eid)
        by_entity[eid] = docs
        n_mentions += len(docs)
    _log.info("mention_matrix.built", n_entities=len(by_entity), n_mentions=n_mentions)
    return MentionLineage(by_entity=by_entity, n_mentions=n_mentions)


def _property_name(store: KuzuGraphStore, property_id: str) -> str:
    """Resolve ``property_id`` to a Measurement ``property_name`` (§25.7).

    Accepts either a ``Property`` node id (resolved via its ``property_name`` /
    ``name`` field) or a bare property-name string (used as-is when no node).
    """
    nd = store.get_node(property_id)
    if nd:
        return nd.get("property_name") or nd.get("name") or property_id
    return property_id


def _has_observation(store: KuzuGraphStore, material_id: str, property_name: str) -> bool:
    """True if a Measurement of ``property_name`` sits within N hops of the material."""
    depth = DEFAULT_OBSERVATION_DEPTH
    rows = store.rows(
        f"MATCH (m:Node {{id:$mid}})-[:Rel*1..{depth}]-(meas:Node) "
        "WHERE meas.label='Measurement' AND meas.property_name=$prop "
        "RETURN meas.id LIMIT 1",
        {"mid": material_id, "prop": property_name},
    )
    return bool(rows)


def mention_value_status(store: KuzuGraphStore, material_id: str, property_id: str) -> bool | None:
    """Does prose that mentions the property actually STATE a value? (§33/N2 gate).

    For every prose ``Chunk-[:MENTIONS]->property`` edge in a document that *also*
    mentions ``material_id``, read the ``value_present`` flag stamped at ingest
    (D1/D2). Three-valued — the caller (:func:`~kg_retrievers.absence_signals.
    classify_cell`, opt-in ``value_gate``) only acts on an explicit ``False``:

    - ``True``  — some qualifying prose edge states a value (``value_present``
      truthy): a real datum was named, so a bare-mention miss stays a
      ``possible_miss``.
    - ``False`` — positive evidence of *no* stated value, in either of two forms:
      (a) the property is co-mentioned but every qualifying edge carries the flag
      and none is truthy (property only named, never measured); or (b) the
      material is discussed yet the property is **never co-mentioned** in its
      prose at all (not even named → a genuine gap, not a missed extraction).
      Because SOTA's :func:`is_mentioned_without_observation` is material-level, an
      un-discussed property reaches ``possible_miss`` here even though it deserves
      ``genuine_gap`` — this is the property-aware refinement the gate applies.
    - ``None``  — unknown: the material is not mentioned, the property is
      unresolvable (bare name, no node), or some qualifying edge lacks the flag (a
      structural / catalog / pre-N2 edge, whose ``value_present`` is ``NULL``).
      "Do not downgrade on absence of evidence."

    ``property_id`` must be the ``Property`` **node id** the MENTIONS edge targets.
    The query is wrapped defensively — a store predating the ``value_present``
    column returns ``None`` rather than raising.
    """
    try:
        docs = documents_mentioning(store, material_id)
        if not docs:
            return None
        if store.get_node(property_id) is None:
            return None  # unresolvable property (bare name) → cannot gate on it
        rows = store.rows(
            "MATCH (d:Node)-[r1:Rel]->(c:Node)-[rm:Rel]->(p:Node {id:$pid}) "
            "WHERE d.label='Document' AND r1.type=$has AND c.label='Chunk' "
            "AND rm.type=$men AND d.id IN $docs "
            "RETURN rm.value_present",
            {"pid": property_id, "has": HAS_CHUNK_TYPE, "men": MENTIONS_TYPE, "docs": docs},
        )
    except Exception:  # store without the value_present column / other read error
        return None
    vals = [r[0] for r in rows]
    if any(v is True for v in vals):
        return True  # a prose doc states a value → keep possible_miss
    # No stated value: either the property is co-mentioned but flagged valueless
    # (all non-null, none truthy) OR never co-mentioned at all (empty → vacuously
    # all non-null). Both are positive evidence of a genuine gap.
    if all(v is not None for v in vals):
        return False  # flagged-valueless, or never co-mentioned (empty) → genuine gap
    return None  # some co-mention edge lacks the flag → cannot be sure


def is_mentioned_without_observation(
    store: KuzuGraphStore, material_id: str, property_id: str
) -> bool:
    """*possible_miss* signal: mentioned but never measured (§25.7 / §25.11).

    Returns ``True`` when ``material_id`` is MENTIONED in at least one document yet
    has **no** ``Measurement`` (наблюдение) of the property (``property_id`` is a
    ``Property`` node id or a bare property name). Returns ``False`` when the
    material is not mentioned at all, or when an observation of the property does
    exist. This is the weakest gap signal: mention with no measurement is where
    the extractor most plausibly missed a datum, not a confident real absence.
    """
    if not documents_mentioning(store, material_id):
        return False
    property_name = _property_name(store, property_id)
    return not _has_observation(store, material_id, property_name)
