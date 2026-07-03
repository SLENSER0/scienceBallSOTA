"""Тесты нормализации узлов/рёбер графа под §5.3 (§14.6).

Ручные, проверяемые кейсы для :mod:`api_gateway.graph_element_normalize`:
белый список типов узлов, обязательные поля и коэрсия булевых/целых значений.

Hand-checkable cases for the §14.6 §5.3 graph normalizer: node-type whitelist,
required fields, and boolean/int coercion.
"""

from __future__ import annotations

import pytest
from api_gateway.graph_element_normalize import (
    NODE_TYPES,
    GraphEdge,
    GraphNode,
    normalize_edge,
    normalize_node,
)


def test_node_type_material_returns_six_keys() -> None:
    """(1) Узел ``Material`` даёт ровно 6 ключей / node yields exactly 6 keys."""
    out = normalize_node({"id": "m1", "label": "Steel", "type": "Material"})
    assert set(out) == {
        "id",
        "label",
        "type",
        "confidence",
        "evidenceCount",
        "verified",
    }
    assert len(out) == 6
    assert out["id"] == "m1"
    assert out["label"] == "Steel"
    assert out["type"] == "Material"


def test_node_type_widget_raises() -> None:
    """(2) Тип вне белого списка → ValueError / non-whitelisted type raises."""
    with pytest.raises(ValueError):
        normalize_node({"id": "x1", "type": "Widget"})


def test_node_missing_id_raises() -> None:
    """(3) Отсутствие ``id`` → ValueError / missing id raises."""
    with pytest.raises(ValueError):
        normalize_node({"type": "Material"})


def test_node_defaults_evidence_count_and_verified() -> None:
    """(4) ``evidenceCount``=0 и ``verified``=False по умолчанию / defaults."""
    out = normalize_node({"id": "m2", "type": "Property"})
    assert out["evidenceCount"] == 0
    assert out["verified"] is False


def test_edge_defaults_inferred_contradicted_evidence_ids() -> None:
    """(5) inferred/contradicted=False, evidenceIds=[] по умолчанию / defaults."""
    out = normalize_edge({"id": "e1", "source": "a", "target": "b"})
    assert out["inferred"] is False
    assert out["contradicted"] is False
    assert out["evidenceIds"] == []


def test_edge_evidence_ids_list_preserved() -> None:
    """(6) Список ``evidenceIds`` сохраняется / evidence id list preserved."""
    out = normalize_edge({"id": "e2", "source": "a", "target": "b", "evidenceIds": ["ev1", "ev2"]})
    assert out["evidenceIds"] == ["ev1", "ev2"]


def test_node_confidence_defaults_zero() -> None:
    """(7) ``confidence`` отсутствует → 0.0 / absent confidence defaults to 0.0."""
    out = normalize_node({"id": "m3", "type": "Experiment"})
    assert out["confidence"] == 0.0
    assert isinstance(out["confidence"], float)


def test_edge_missing_source_raises() -> None:
    """(8) Ребро без ``source`` → ValueError / missing edge source raises."""
    with pytest.raises(ValueError):
        normalize_edge({"id": "e3", "target": "b"})


def test_edge_missing_target_raises() -> None:
    """Ребро без ``target`` → ValueError / missing edge target raises."""
    with pytest.raises(ValueError):
        normalize_edge({"id": "e4", "source": "a"})


def test_edge_missing_id_raises() -> None:
    """Ребро без ``id`` → ValueError / missing edge id raises."""
    with pytest.raises(ValueError):
        normalize_edge({"source": "a", "target": "b"})


def test_node_all_types_accepted() -> None:
    """Каждый тип из белого списка проходит / every whitelisted type accepted."""
    expected = {
        "Material",
        "Experiment",
        "ProcessingRegime",
        "Property",
        "Equipment",
        "Paper",
        "Claim",
        "Lab",
        "Person",
        "Gap",
    }
    assert expected == NODE_TYPES
    for node_type in NODE_TYPES:
        out = normalize_node({"id": "n", "type": node_type})
        assert out["type"] == node_type


def test_node_label_defaults_to_id() -> None:
    """``label`` по умолчанию равен ``id`` / label defaults to the id."""
    out = normalize_node({"id": "m9", "type": "Lab"})
    assert out["label"] == "m9"


def test_node_boolean_and_int_coercion() -> None:
    """Коэрсия истинностных значений / truthy inputs coerce to bool and int."""
    out = normalize_node(
        {
            "id": "m10",
            "type": "Claim",
            "verified": 1,
            "evidenceCount": "5",
            "confidence": "0.75",
        }
    )
    assert out["verified"] is True
    assert out["evidenceCount"] == 5
    assert out["confidence"] == 0.75


def test_edge_returns_ten_keys() -> None:
    """Ребро отдаёт ровно 10 ключей §5.3 / edge yields exactly 10 §5.3 keys."""
    out = normalize_edge({"id": "e5", "source": "a", "target": "b", "type": "SUPPORTS"})
    assert set(out) == {
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
    assert len(out) == 10


def test_edge_scalar_evidence_id_wrapped() -> None:
    """Скалярный ``evidenceIds`` оборачивается в список / scalar wrapped in list."""
    out = normalize_edge({"id": "e6", "source": "a", "target": "b", "evidenceIds": "ev9"})
    assert out["evidenceIds"] == ["ev9"]


def test_dataclass_as_dict_roundtrip() -> None:
    """Frozen-датаклассы дают ту же wire-форму / dataclass as_dict matches."""
    node = GraphNode(
        id="m1",
        label="Steel",
        type="Material",
        confidence=0.0,
        evidence_count=0,
        verified=False,
    )
    raw_node = {"id": "m1", "label": "Steel", "type": "Material"}
    assert node.as_dict() == normalize_node(raw_node)
    edge = GraphEdge(
        id="e1",
        source="a",
        target="b",
        label="",
        type="",
        confidence=0.0,
        evidence_count=0,
        inferred=False,
        contradicted=False,
        evidence_ids=[],
    )
    assert edge.as_dict() == normalize_edge({"id": "e1", "source": "a", "target": "b"})
