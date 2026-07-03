"""Tests for §17.8 GraphLegend visual-encoding builder (§5.2.3/§5.3).

Hand-checkable: fixtures below are encoded §5.3 ``GraphResponse`` dicts (as produced by
:func:`kg_retrievers.graph_dto.build_graph_response`); assertions verify type counting,
ordering (desc count, then alphabetical), the fixed 8-channel catalogue and JSON round
trip.
"""

from __future__ import annotations

import json

from kg_retrievers.graph_legend import (
    ENCODING_RULES,
    LegendSpec,
    build_legend,
)


def _payload() -> dict:
    """2 Material + 1 Paper nodes; IMPROVES x3 + MEASURED_PROPERTY x1 edges (§5.3)."""
    return {
        "nodes": [
            {"id": "m1", "type": "Material", "label": "TiO2"},
            {"id": "m2", "type": "Material", "label": "SiC"},
            {"id": "p1", "type": "Paper", "label": "Doi 10.x"},
        ],
        "edges": [
            {"id": "e1", "source": "m1", "target": "p1", "type": "IMPROVES"},
            {"id": "e2", "source": "m2", "target": "p1", "type": "IMPROVES"},
            {"id": "e3", "source": "m1", "target": "m2", "type": "IMPROVES"},
            {"id": "e4", "source": "m1", "target": "p1", "type": "MEASURED_PROPERTY"},
        ],
    }


def test_node_types_counted_and_ordered() -> None:
    spec = build_legend(_payload())
    assert spec.node_types[0] == {"type": "Material", "count": 2, "visible": True}
    paper = next(e for e in spec.node_types if e["type"] == "Paper")
    assert paper["count"] == 1
    assert paper["visible"] is True
    assert [e["type"] for e in spec.node_types] == ["Material", "Paper"]


def test_edge_types_ordered_by_count() -> None:
    spec = build_legend(_payload())
    assert [e["type"] for e in spec.edge_types] == ["IMPROVES", "MEASURED_PROPERTY"]
    assert spec.edge_types[0] == {"type": "IMPROVES", "count": 3, "visible": True}
    assert spec.edge_types[1]["count"] == 1


def test_encodings_are_the_eight_channels() -> None:
    spec = build_legend(_payload())
    assert len(spec.encodings) == 8
    assert len(ENCODING_RULES) == 8
    for rule in spec.encodings:
        assert set(rule.keys()) == {"channel", "encodes", "description_ru"}
    channels = [r["channel"] for r in spec.encodings]
    assert channels == [
        "nodeColor",
        "nodeSize",
        "hollowNode",
        "lockIcon",
        "edgeThickness",
        "edgeOpacity",
        "dashedEdge",
        "redEdge",
    ]
    by_channel = {r["channel"]: r["encodes"] for r in spec.encodings}
    assert by_channel["nodeColor"] == "type"
    assert by_channel["nodeSize"] == "evidenceCount"
    assert by_channel["hollowNode"] == "missingFields"
    assert by_channel["lockIcon"] == "verified"
    assert by_channel["edgeThickness"] == "evidenceCount"
    assert by_channel["edgeOpacity"] == "confidence"
    assert by_channel["dashedEdge"] == "inferred"
    assert by_channel["redEdge"] == "contradicted"


def test_absent_type_never_appears() -> None:
    spec = build_legend(_payload())
    present = {e["type"] for e in spec.node_types}
    assert "Experiment" not in present
    assert "Claim" not in present
    edge_present = {e["type"] for e in spec.edge_types}
    assert "CONTRADICTS" not in edge_present


def test_empty_payload_keeps_encodings() -> None:
    spec = build_legend({"nodes": [], "edges": []})
    assert spec.node_types == ()
    assert spec.edge_types == ()
    assert len(spec.encodings) == 8
    # Missing keys entirely behave the same as empty lists.
    spec2 = build_legend({})
    assert spec2.node_types == ()
    assert spec2.edge_types == ()
    assert len(spec2.encodings) == 8


def test_stable_alphabetical_order_on_ties() -> None:
    payload = {
        "nodes": [
            {"id": "1", "type": "Zeta"},
            {"id": "2", "type": "Alpha"},
            {"id": "3", "type": "Mu"},
        ],
        "edges": [],
    }
    spec = build_legend(payload)
    # All count==1 → alphabetical by type.
    assert [e["type"] for e in spec.node_types] == ["Alpha", "Mu", "Zeta"]
    assert all(e["count"] == 1 for e in spec.node_types)


def test_edge_type_falls_back_to_label() -> None:
    payload = {
        "nodes": [],
        "edges": [
            {"id": "e1", "source": "a", "target": "b", "label": "RELATED_TO"},
            {"id": "e2", "source": "b", "target": "c", "type": "IMPROVES"},
        ],
    }
    spec = build_legend(payload)
    types = {e["type"]: e["count"] for e in spec.edge_types}
    assert types == {"RELATED_TO": 1, "IMPROVES": 1}


def test_as_dict_camelcase_json_roundtrip() -> None:
    spec = build_legend(_payload())
    out = spec.as_dict()
    assert set(out.keys()) == {"nodeTypes", "edgeTypes", "encodings"}
    assert out["nodeTypes"][0]["type"] == "Material"
    assert out["edgeTypes"][0]["type"] == "IMPROVES"
    assert len(out["encodings"]) == 8
    # Every toggle defaults on.
    assert all(e["visible"] is True for e in out["nodeTypes"])
    assert all(e["visible"] is True for e in out["edgeTypes"])
    # Round-trips through JSON without error.
    restored = json.loads(json.dumps(out))
    assert restored == out


def test_is_frozen_dataclass() -> None:
    spec = build_legend({})
    assert isinstance(spec, LegendSpec)
    try:
        spec.node_types = ()  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("LegendSpec must be frozen")
