"""Graph legend: all 8 §5.2.3 visual codes + toggleable node/edge categories.

The existing ``/api/v1/graph/encoding/legend`` (see ``graph_encoding.py``) serves
the SEVEN *derived* visual codes (hollow / red / dashed / lock / node-size /
edge-width / edge-opacity). This router adds the missing **8th** code —
``node colour = entity type`` — so the frontend ``GraphLegend`` can decode the
full visual language of the «клубок», and it enumerates the **categories**
actually present in a live graph (node labels + relation types, with counts) so
the UI can render a checkbox per category to toggle its visibility.

Everything is served from the live traversal store (server / Neo4j :8000 profile)
and passed through the shared, pure :func:`enrich_visual_encoding` transformer, so
the sample graph the legend renders carries every §5.2.3 field already filled.

Endpoints
---------
* ``GET /api/v1/graph/legend/codes`` — machine-readable list of all 8 codes plus
  the entity-type → colour map that decodes the ``node colour`` channel.
* ``GET /api/v1/graph/legend/view`` — an encoded sample (or entity-seeded)
  neighbourhood together with its node-category and edge-category facets (each
  ``{type, count}``) — the data the toggle checkboxes act on.

Only NEW code: traversal + enrichment are delegated to the shared store and the
existing pure encoder; no raw Cypher is accepted from clients.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from api_gateway.graph_visual_encoding import (
    VISUAL_ENCODING_LEGEND,
    enrich_visual_encoding,
)
from kg_common import GraphResponse
from kg_common.dto import CamelModel

router = APIRouter(prefix="/api/v1/graph/legend", tags=["graph"])

# The 8th visual code (§5.2.3 «node color = entity type»), which the derived-codes
# legend in graph_encoding.py does not carry because it is a categorical channel,
# not a derived boolean/scalar. Kept first so the legend reads colour → shape →
# stroke → scale, top to bottom.
_NODE_COLOUR_CODE: dict[str, str] = {
    "key": "node_colour",
    "channel": "node fill colour",
    "signal": "type",
    "label": "Цвет узла — тип сущности",
    "meaning": "Каждой метке (Material, Property, Method, …) соответствует свой цвет.",
}

# Entity-type → colour, kept in parity with the frontend canvas renderer
# (GraphView.TYPE_COLOR) so the legend swatches and the «клубок» agree 1:1. This
# is the machine-readable decode of the categorical ``node colour`` channel.
NODE_TYPE_COLOURS: dict[str, str] = {
    "Material": "#8FA3B0",
    "ChemicalElement": "#8FA3B0",
    "TechnologySolution": "#C87941",
    "Method": "#C87941",
    "ProcessingRegime": "#E89B5C",
    "Equipment": "#B9CAD4",
    "Measurement": "#E89B5C",
    "Property": "#8FA3B0",
    "Evidence": "#5A6270",
    "Paper": "#6C8CD5",
    "Document": "#6C8CD5",
    "Gap": "#E0A23C",
    "Contradiction": "#E5484D",
    "Person": "#B9CAD4",
    "Lab": "#B9CAD4",
}
_DEFAULT_COLOUR = "#8FA3B0"


class Category(CamelModel):
    """A togglable node-label / relation-type category present in the graph."""

    type: str
    count: int
    colour: str | None = None  # set for node categories; None for edge categories


class LegendView(CamelModel):
    """An encoded sample graph plus the categories its checkboxes can toggle."""

    graph: GraphResponse
    node_categories: list[Category]
    edge_categories: list[Category]
    summary: dict[str, int]
    seed: str | None = None


def _summary(resp: GraphResponse) -> dict[str, int]:
    return {
        "nodes": len(resp.nodes),
        "edges": len(resp.edges),
        "node_types": len({n.type for n in resp.nodes}),
        "edge_types": len({str(e.type) for e in resp.edges}),
        "hollow": sum(1 for n in resp.nodes if n.missing_fields),
        "verified": sum(1 for n in resp.nodes if n.verified),
        "contradicted": sum(1 for e in resp.edges if e.contradicted),
        "inferred": sum(1 for e in resp.edges if e.inferred),
    }


def _facets(resp: GraphResponse) -> tuple[list[Category], list[Category]]:
    """Group nodes by label and edges by relation type, most frequent first."""
    node_counts: Counter[str] = Counter(n.type for n in resp.nodes)
    edge_counts: Counter[str] = Counter(str(e.type) for e in resp.edges)
    nodes = [
        Category(type=t, count=c, colour=NODE_TYPE_COLOURS.get(t, _DEFAULT_COLOUR))
        for t, c in node_counts.most_common()
    ]
    edges = [Category(type=t, count=c) for t, c in edge_counts.most_common()]
    return nodes, edges


def _busiest_seed(store: Any) -> str | None:
    rows = store.rows(
        "MATCH (n:Node)-[r:Rel]-() RETURN n.id, count(r) AS d ORDER BY d DESC LIMIT 1"
    )
    if not rows or not rows[0] or rows[0][0] is None:
        return None
    return rows[0][0]


@router.get("/codes")
def codes() -> dict[str, Any]:
    """All 8 §5.2.3 visual codes + the entity-type colour map decoding channel 8."""
    encodings: list[dict[str, str]] = [_NODE_COLOUR_CODE, *VISUAL_ENCODING_LEGEND]
    return {
        "encodings": encodings,
        "count": len(encodings),
        "node_type_colours": NODE_TYPE_COLOURS,
    }


@router.get("/view", response_model=LegendView)
def view(
    entity_id: str | None = Query(default=None),
    depth: int = Query(default=2, ge=1, le=3),
) -> LegendView:
    """Encoded neighbourhood + category facets for the legend's toggle checkboxes.

    Without ``entity_id`` the busiest node's neighbourhood is used, so the legend
    always has live data to demonstrate the codes and populate the toggles.
    """
    store = get_store()
    if entity_id is not None:
        if store.get_node(entity_id) is None:
            raise HTTPException(status_code=404, detail=f"entity {entity_id!r} not found")
        seed = entity_id
    else:
        seed = _busiest_seed(store)
        if seed is None:
            empty = GraphResponse()
            return LegendView(
                graph=empty,
                node_categories=[],
                edge_categories=[],
                summary=_summary(empty),
                seed=None,
            )
    resp = enrich_visual_encoding(store.neighbors(seed, depth=depth))
    node_cats, edge_cats = _facets(resp)
    return LegendView(
        graph=resp,
        node_categories=node_cats,
        edge_categories=edge_cats,
        summary=_summary(resp),
        seed=seed,
    )
