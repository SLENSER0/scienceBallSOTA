"""Fill the §5.2.3 visual-encoding fields on a graph payload (§3.16).

The live traversal payload (``store.neighbors`` / ``store.subgraph_from_ids``)
returns nodes/edges with ``confidence``/``verified``/``inferred``/``contradicted``
copied straight from stored properties, but three of the four §5.2.3 visual codes
are *derived*, not stored, and were left empty:

* **hollow node = «нет данных»** → ``GraphNode.missing_fields`` — the required
  domain properties absent for the node's label. Computed from the single source
  of truth :func:`kg_schema.node_validation.missing_fields`; a non-empty list makes
  the frontend draw the node hollow (``GraphView`` line: ``hollow = type==='Gap' ||
  missingFields.length>0``).
* **красное ребро = противоречие** → ``GraphEdge.contradicted`` — any edge whose
  relation type is ``CONTRADICTS`` is a contradiction edge and must render red,
  regardless of whether a stored ``contradicted`` flag was set.
* **node/edge size = evidence count** → ``evidence_count`` — nodes size on the
  amount of evidence backing them; edges thicken with their ``evidence_ids``.

``inferred`` (dashed) and ``verified`` (lock) are already carried verbatim from
stored properties by the store DTO mapping, so they need no derivation here.

This module is a **pure** transformer over a :class:`~kg_common.GraphResponse`:
no store access, no I/O — so it is trivially testable and can wrap the output of
either backend (Kuzu or Neo4j server profile). Enrichment is idempotent.
"""

from __future__ import annotations

from kg_common import GraphResponse
from kg_schema.node_validation import missing_fields

# Relation types that ARE a contradiction (red edge §5.2.3). Kept as a set so a
# future symmetric/typed contradiction relation can be added in one place.
_CONTRADICTION_RELS = {"CONTRADICTS"}

# The machine-readable legend the UI renders so the visual language is self-
# explanatory. Order = reading order in the legend card.
VISUAL_ENCODING_LEGEND: list[dict[str, str]] = [
    {
        "key": "hollow",
        "channel": "node fill",
        "signal": "missingFields",
        "label": "Полый узел — нет данных",
        "meaning": "У сущности отсутствуют обязательные поля её метки (§3.18).",
    },
    {
        "key": "contradiction",
        "channel": "edge colour",
        "signal": "contradicted",
        "label": "Красное ребро — противоречие",
        "meaning": "Связь CONTRADICTS между конфликтующими утверждениями/измерениями.",
    },
    {
        "key": "inferred",
        "channel": "edge stroke",
        "signal": "inferred",
        "label": "Пунктир — выведено (inferred)",
        "meaning": "Связь получена выводом/курированием, а не прямой экстракцией.",
    },
    {
        "key": "verified",
        "channel": "node ring / lock",
        "signal": "verified",
        "label": "Замок — проверено (verified)",
        "meaning": "Сущность подтверждена куратором (review_status accepted/corrected).",
    },
    {
        "key": "node_size",
        "channel": "node radius",
        "signal": "evidenceCount",
        "label": "Размер узла — объём доказательств",
        "meaning": "Больше evidence backing — крупнее узел.",
    },
    {
        "key": "edge_width",
        "channel": "edge width",
        "signal": "evidenceCount",
        "label": "Толщина ребра — объём доказательств",
        "meaning": "Больше evidence_ids у связи — толще ребро.",
    },
    {
        "key": "edge_opacity",
        "channel": "edge opacity",
        "signal": "confidence",
        "label": "Прозрачность ребра — уверенность",
        "meaning": "Чем ниже confidence, тем бледнее связь.",
    },
]


def _node_missing_fields(node) -> list[str]:  # type: ignore[no-untyped-def]
    """Required properties absent for a node's label (§3.18).

    Reconstructs a flat node dict from the DTO (``type`` carries the label,
    ``properties`` the domain props) so the shared validator can be reused without
    a store round-trip. Returns ``[]`` for labels with no declared requirements.
    """
    flat: dict = {"label": node.type}
    if node.properties:
        flat.update(node.properties)
    return missing_fields(flat)


def _evidence_from(props: dict | None) -> set[str]:
    """Collect evidence ids from a props dict, tolerating several key spellings."""
    out: set[str] = set()
    if not props:
        return out
    for key in ("evidence_ids", "evidenceIds", "evidence"):
        val = props.get(key)
        if isinstance(val, list):
            out.update(str(x) for x in val if x)
    return out


def enrich_visual_encoding(resp: GraphResponse) -> GraphResponse:
    """Populate the derived §5.2.3 visual-encoding fields on ``resp`` in place.

    * ``node.missing_fields`` ← required props absent for the node's label.
    * ``node.evidence_count`` ← distinct evidence ids on the node itself plus the
      evidence carried by every incident edge (node size = evidence backing).
    * ``edge.evidence_count`` ← ``len(evidence_ids)``.
    * ``edge.contradicted`` ← ``True`` for ``CONTRADICTS`` edges (red edge),
      preserving any already-``True`` stored flag.

    Returns the same object for call chaining.
    """
    # Per-node evidence accumulator (node's own evidence + incident-edge evidence).
    node_ev: dict[str, set[str]] = {n.id: set() for n in resp.nodes}

    for edge in resp.edges:
        ev = set(edge.evidence_ids or [])
        edge.evidence_count = len(ev)
        if str(edge.type).upper() in _CONTRADICTION_RELS:
            edge.contradicted = True
        # An edge's evidence backs both endpoints it connects.
        for endpoint in (edge.source, edge.target):
            if endpoint in node_ev:
                node_ev[endpoint].update(ev)

    for node in resp.nodes:
        node.missing_fields = _node_missing_fields(node)
        own = _evidence_from(node.properties)
        node.evidence_count = len(node_ev.get(node.id, set()) | own)

    return resp


__all__ = ["VISUAL_ENCODING_LEGEND", "enrich_visual_encoding"]
