"""Tests for §5.2.3 / §17.8 Graph Explorer hover tooltip builders.

Проверяем чистые билдеры node_tooltip/edge_tooltip: заголовок, evidenceCount по
умолчанию, verified/missingFields (hollow), sourceCount из evidenceIds vs evidenceCount,
confidence по умолчанию None. Hand-checkable, без БД.
"""

from __future__ import annotations

from kg_retrievers.graph_tooltip import (
    EdgeTooltip,
    NodeTooltip,
    edge_tooltip,
    node_tooltip,
)


def test_node_full_payload() -> None:
    node = {
        "label": "Al-2024",
        "type": "Material",
        "evidenceCount": 5,
        "verified": True,
        "missingFields": [],
    }
    tip = node_tooltip(node)
    assert isinstance(tip, NodeTooltip)
    assert tip.title == "Al-2024"
    assert tip.type == "Material"
    assert tip.evidence_count == 5
    assert tip.verified is True
    assert tip.missing_fields == ()
    assert tip.as_dict() == {
        "title": "Al-2024",
        "type": "Material",
        "evidenceCount": 5,
        "verified": True,
        "missingFields": [],
    }


def test_node_missing_evidence_count_defaults_zero() -> None:
    node = {"label": "X", "type": "Material", "verified": False}
    tip = node_tooltip(node)
    assert tip.evidence_count == 0
    assert tip.verified is False
    assert tip.missing_fields == ()
    assert tip.as_dict()["evidenceCount"] == 0


def test_node_missing_fields_tuple_and_dict() -> None:
    node = {"label": "Y", "type": "Material", "missingFields": ["name"]}
    tip = node_tooltip(node)
    assert tip.missing_fields == ("name",)
    assert tip.as_dict()["missingFields"] == ["name"]
    # as_dict must copy, not alias the frozen tuple/state.
    tip.as_dict()["missingFields"].append("hack")
    assert tip.missing_fields == ("name",)


def test_node_title_falls_back_to_name_then_id() -> None:
    assert node_tooltip({"name": "FromName", "type": "Material"}).title == "FromName"
    assert node_tooltip({"id": "n1", "type": "Material"}).title == "n1"


def test_node_verified_absent_is_false() -> None:
    assert node_tooltip({"label": "Z", "type": "Material"}).verified is False


def test_edge_source_count_from_evidence_ids() -> None:
    edge = {"type": "IMPROVES", "confidence": 0.8, "evidenceIds": ["e1", "e2"]}
    tip = edge_tooltip(edge)
    assert isinstance(tip, EdgeTooltip)
    assert tip.relation_type == "IMPROVES"
    assert tip.source_count == 2
    assert tip.confidence == 0.8
    assert tip.as_dict() == {
        "relationType": "IMPROVES",
        "confidence": 0.8,
        "sourceCount": 2,
    }


def test_edge_source_count_falls_back_to_evidence_count() -> None:
    edge = {"type": "IMPROVES", "confidence": 0.5, "evidenceCount": 3}
    tip = edge_tooltip(edge)
    assert tip.source_count == 3


def test_edge_empty_evidence_ids_uses_evidence_count() -> None:
    edge = {"type": "IMPROVES", "evidenceIds": [], "evidenceCount": 4}
    assert edge_tooltip(edge).source_count == 4


def test_edge_missing_confidence_is_none() -> None:
    edge = {"type": "IMPROVES", "evidenceIds": ["e1"]}
    tip = edge_tooltip(edge)
    assert tip.confidence is None
    assert tip.as_dict()["confidence"] is None
    assert tip.source_count == 1


def test_edge_relation_type_falls_back_to_label() -> None:
    edge = {"label": "improves", "evidenceCount": 1}
    assert edge_tooltip(edge).relation_type == "improves"


def test_edge_no_source_info_defaults_zero() -> None:
    edge = {"type": "IMPROVES", "confidence": 0.9}
    tip = edge_tooltip(edge)
    assert tip.source_count == 0
    assert tip.confidence == 0.9
