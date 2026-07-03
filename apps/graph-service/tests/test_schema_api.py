"""Graph-payload schema validation + DTO helpers (§3.16)."""

from __future__ import annotations

from graph_service.schema_api import (
    RelSignature,
    build_schema_descriptor,
    coerce_graph_response,
    validate_graph_response,
)

from kg_common.dto import GraphResponse


def _node(nid: str, ntype: str, label: str = "узел") -> dict[str, str]:
    return {"id": nid, "label": label, "type": ntype}


def _edge(eid: str, src: str, tgt: str, rtype: str, label: str = "связь") -> dict[str, str]:
    return {"id": eid, "source": src, "target": tgt, "label": label, "type": rtype}


def test_valid_small_graph_passes() -> None:
    payload = {
        "nodes": [_node("m1", "Measurement", "Твёрдость"), _node("p1", "Property", "Hardness")],
        "edges": [_edge("e1", "m1", "p1", "OF_PROPERTY")],
    }
    result = validate_graph_response(payload)
    assert result["valid"] is True
    assert result["errors"] == []


def test_unknown_node_type_flagged() -> None:
    payload = {"nodes": [_node("x1", "Unicorn")], "edges": []}
    result = validate_graph_response(payload)
    assert result["valid"] is False
    assert any("Unicorn" in err for err in result["errors"])


def test_dangling_edge_source_flagged() -> None:
    payload = {
        "nodes": [_node("p1", "Property")],
        "edges": [_edge("e1", "ghost", "p1", "OF_PROPERTY")],
    }
    result = validate_graph_response(payload)
    assert result["valid"] is False
    assert any("ghost" in err and "source" in err for err in result["errors"])


def test_dangling_edge_target_flagged() -> None:
    payload = {
        "nodes": [_node("m1", "Measurement")],
        "edges": [_edge("e1", "m1", "phantom", "OF_PROPERTY")],
    }
    result = validate_graph_response(payload)
    assert result["valid"] is False
    assert any("phantom" in err and "target" in err for err in result["errors"])


def test_unknown_rel_type_flagged() -> None:
    payload = {
        "nodes": [_node("m1", "Measurement"), _node("p1", "Property")],
        "edges": [_edge("e1", "m1", "p1", "FLIES_TO")],
    }
    result = validate_graph_response(payload)
    assert result["valid"] is False
    assert any("FLIES_TO" in err for err in result["errors"])


def test_schema_descriptor_lists_labels_and_relationships() -> None:
    desc = build_schema_descriptor()
    assert desc["labelCount"] >= 33
    assert len(desc["labels"]) >= 33
    assert len(desc["relationships"]) >= 33
    assert "Material" in desc["labels"]
    assert "OF_PROPERTY" in desc["relationshipTypes"]
    first = desc["relationships"][0]
    assert set(first) == {"from", "rel", "to"}


def test_coerce_builds_valid_graph_response() -> None:
    graph = coerce_graph_response(
        nodes=[_node("m1", "Measurement"), _node("p1", "Property")],
        edges=[_edge("e1", "m1", "p1", "OF_PROPERTY")],
    )
    assert isinstance(graph, GraphResponse)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    # The coerced DTO round-trips through the validator as valid.
    result = validate_graph_response(graph.model_dump(by_alias=True))
    assert result["valid"] is True


def test_empty_graph_valid() -> None:
    result = validate_graph_response({"nodes": [], "edges": []})
    assert result["valid"] is True
    assert result["errors"] == []


def test_rel_signature_as_dict() -> None:
    sig = RelSignature("Measurement", "OF_PROPERTY", "Property")
    assert sig.as_dict() == {"from": "Measurement", "rel": "OF_PROPERTY", "to": "Property"}
