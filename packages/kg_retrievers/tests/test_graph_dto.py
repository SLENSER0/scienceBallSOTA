"""Tests for the node/edge → frontend GraphResponse DTO (§3.14/§5.2.3/§5.3).

Hand-checks the camelCase payload keys, the visual-encoding mappings (verified from
``review_status``, ``missingFields`` from missing required props, ``contradicted`` from
the ``CONTRADICTS`` type, ``inferred``/``evidenceIds`` passthrough) and the
``build_graph_response`` shape, then cross-validates each payload against the frozen
:mod:`kg_common.dto` Pydantic contract.
"""

from __future__ import annotations

from kg_common.dto import GraphEdge, GraphNode, GraphResponse
from kg_retrievers.graph_dto import (
    build_graph_response,
    edge_to_dto,
    node_to_dto,
)

# Exact §5.3 camelCase key sets the payloads must emit (single source of truth).
_NODE_KEYS = {
    "id",
    "label",
    "type",
    "confidence",
    "evidenceCount",
    "verified",
    "missingFields",
    "communityId",
    "properties",
}
_EDGE_KEYS = {
    "id",
    "source",
    "target",
    "label",
    "type",
    "confidence",
    "evidenceCount",
    "inferred",
    "contradicted",
    "evidenceIds",
}


def test_node_dto_camel_keys_and_evidence_count() -> None:
    # raw store node: "label" column is the NodeLabel (→ type), "name" is the display.
    node = {
        "id": "mat-steel",
        "label": "Material",
        "name": "Сталь",
        "confidence": 0.75,
        "evidence_count": 3,
        "community_id": 4,
        "hardness_hv": 210,
    }
    dto = node_to_dto(node)
    assert set(dto) == _NODE_KEYS
    assert dto["id"] == "mat-steel"
    assert dto["type"] == "Material"  # from the raw "label" column
    assert dto["label"] == "Сталь"  # display from "name"
    assert dto["confidence"] == 0.75
    assert dto["evidenceCount"] == 3  # node size encoding (§5.2.3)
    assert dto["communityId"] == 4
    # non-reserved props are swept into the properties bag; name/label/type are not
    assert dto["properties"] == {"hardness_hv": 210}
    # the payload satisfies the frozen kg_common.dto contract (camelCase aliases)
    GraphNode.model_validate(dto)


def test_verified_from_review_status() -> None:
    def verified(status: str | None) -> bool:
        node = {"id": "n", "label": "Material", "name": "X"}
        if status is not None:
            node["review_status"] = status
        return node_to_dto(node)["verified"]

    assert verified("accepted") is True  # human-reviewed → lock icon (§5.2.3)
    assert verified("corrected") is True
    assert verified("verified") is True  # permissive legacy alias
    assert verified("pending") is False
    assert verified("rejected") is False
    assert verified(None) is False  # no review_status → not verified


def test_missing_fields_populated() -> None:
    # a Material with no name is incomplete → hollow node, missingFields == ["name"]
    incomplete = node_to_dto({"id": "m1", "label": "Material"})
    assert incomplete["missingFields"] == ["name"]
    # a fully-specified Material has no missing required props
    complete = node_to_dto({"id": "m2", "label": "Material", "name": "Медь"})
    assert complete["missingFields"] == []
    # Measurement requires value+unit; only unit present → value flagged missing
    meas = node_to_dto({"id": "meas1", "label": "Measurement", "unit": "HV"})
    assert meas["missingFields"] == ["value"]
    # an explicit missing_fields list is passed straight through (curation override)
    override = node_to_dto(
        {"id": "m3", "label": "Material", "name": "Fe", "missing_fields": ["source"]}
    )
    assert override["missingFields"] == ["source"]


def test_edge_contradicted_from_type() -> None:
    contra = edge_to_dto({"id": "e1", "source": "c1", "target": "c2", "type": "CONTRADICTS"})
    assert contra["contradicted"] is True  # red edge (§5.2.3), from CONTRADICTS
    assert contra["type"] == "CONTRADICTS"
    # a non-contradicting rel type is not flagged
    improves = edge_to_dto({"id": "e2", "source": "a", "target": "b", "type": "IMPROVES"})
    assert improves["contradicted"] is False
    # an explicit contradicted flag also wins even on a different type
    explicit = edge_to_dto(
        {"id": "e3", "source": "a", "target": "b", "type": "RELATED", "contradicted": True}
    )
    assert explicit["contradicted"] is True


def test_edge_inferred_flag() -> None:
    inferred = edge_to_dto(
        {"id": "e1", "source": "a", "target": "b", "type": "IMPROVES", "inferred": True}
    )
    assert inferred["inferred"] is True  # dashed edge (§5.2.3)
    # absent / falsey inferred → solid edge
    solid = edge_to_dto({"id": "e2", "source": "a", "target": "b", "type": "IMPROVES"})
    assert solid["inferred"] is False
    off = edge_to_dto(
        {"id": "e3", "source": "a", "target": "b", "type": "IMPROVES", "inferred": False}
    )
    assert off["inferred"] is False


def test_edge_evidence_ids_passthrough() -> None:
    # list form: evidenceIds pass through and drive evidenceCount (edge thickness)
    edge = edge_to_dto(
        {
            "id": "e1",
            "source": "a",
            "target": "b",
            "type": "SUPPORTS",
            "evidence_ids": ["ev-1", "ev-2"],
        }
    )
    assert set(edge) == _EDGE_KEYS
    assert edge["evidenceIds"] == ["ev-1", "ev-2"]
    assert edge["evidenceCount"] == 2  # thickness derives from the id count (§5.2.3)
    GraphEdge.model_validate(edge)
    # JSON-string form (Kuzu stores list props as JSON) is parsed the same way
    json_edge = edge_to_dto(
        {"source": "a", "target": "b", "type": "SUPPORTS", "evidence_ids": '["ev-9"]'}
    )
    assert json_edge["evidenceIds"] == ["ev-9"]
    # explicit evidence_count wins over the id count when both are given
    counted = edge_to_dto(
        {
            "source": "a",
            "target": "b",
            "type": "SUPPORTS",
            "evidence_ids": ["ev-1"],
            "evidence_count": 7,
        }
    )
    assert counted["evidenceCount"] == 7
    # a missing edge id is synthesised deterministically from source/type/target
    assert json_edge["id"] == "a-SUPPORTS-b"


def test_build_graph_response_shape() -> None:
    nodes = [
        {"id": "mat-steel", "label": "Material", "name": "Сталь", "review_status": "accepted"},
        {"id": "prop-hv", "label": "Property", "name": "Твёрдость"},
    ]
    edges = [
        {
            "id": "e1",
            "source": "mat-steel",
            "target": "prop-hv",
            "type": "HAS_PROPERTY",
            "evidence_ids": ["ev-1"],
        }
    ]
    resp = build_graph_response(nodes, edges)
    assert set(resp) == {"nodes", "edges"}
    assert len(resp["nodes"]) == 2
    assert len(resp["edges"]) == 1
    assert set(resp["nodes"][0]) == _NODE_KEYS
    assert set(resp["edges"][0]) == _EDGE_KEYS
    assert resp["nodes"][0]["verified"] is True
    assert resp["edges"][0]["evidenceCount"] == 1
    # the whole payload validates against the §5.3 GraphResponse contract
    GraphResponse.model_validate(resp)


def test_build_graph_response_empty() -> None:
    resp = build_graph_response([], [])
    assert resp == {"nodes": [], "edges": []}
    GraphResponse.model_validate(resp)


def test_node_type_and_label_fallback() -> None:
    # explicit "type" is preferred over the raw "label" column when both are present
    typed = node_to_dto({"id": "x", "type": "Paper", "label": "Material", "name": "Doc"})
    assert typed["type"] == "Paper"
    # with no display name, the label falls back to the id (never the category)
    unnamed = node_to_dto({"id": "n42", "label": "Person"})
    assert unnamed["label"] == "n42"
    assert unnamed["type"] == "Person"
    # a minimal node still emits every key with sane defaults
    minimal = node_to_dto({"id": "n0"})
    assert set(minimal) == _NODE_KEYS
    assert minimal["confidence"] is None
    assert minimal["evidenceCount"] is None
    assert minimal["verified"] is False
    assert minimal["missingFields"] == []
    assert minimal["properties"] == {}
