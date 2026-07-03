"""Тесты глобального фильтра графа §17.5 / tests for the §17.5 graph filter.

Проверяет предикат :func:`node_matches`, свёртку :func:`apply_graph_filter` и
сериализацию :meth:`GraphFilterState.to_query_params` по ручным примерам из
спецификации §17.5.
"""

from __future__ import annotations

from api_gateway.graph_filter_predicate import (
    GraphFilterState,
    apply_graph_filter,
    node_matches,
)


def test_min_confidence_rejects_low_node() -> None:
    """Узел с confidence 0.4 не проходит порог 0.5 / low confidence fails."""
    state = GraphFilterState(min_confidence=0.5)
    assert node_matches(state, {"confidence": 0.4}) is False
    assert node_matches(state, {"confidence": 0.5}) is True


def test_node_types_rejects_other_type() -> None:
    """node_types=('Material',) отбраковывает узел 'Property'."""
    state = GraphFilterState(node_types=("Material",))
    assert node_matches(state, {"type": "Property"}) is False
    assert node_matches(state, {"type": "Material"}) is True


def test_verified_only_rejects_unverified() -> None:
    """verified_only=True отбраковывает verified False / rejects unverified."""
    state = GraphFilterState(verified_only=True)
    assert node_matches(state, {"verified": False}) is False
    assert node_matches(state, {"verified": True}) is True


def test_empty_node_types_matches_any() -> None:
    """Пустой node_types проходит любой тип / empty node_types matches any."""
    state = GraphFilterState()
    assert node_matches(state, {"type": "Material"}) is True
    assert node_matches(state, {"type": "Property"}) is True
    assert node_matches(state, {}) is True


def test_apply_graph_filter_drops_edge_with_removed_target() -> None:
    """Ребро с отфильтрованным target выпадает / dropped-endpoint edge removed."""
    state = GraphFilterState(node_types=("Material",))
    graph = {
        "nodes": [
            {"id": "n1", "type": "Material"},
            {"id": "n2", "type": "Property"},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    out = apply_graph_filter(state, graph)
    assert [n["id"] for n in out["nodes"]] == ["n1"]
    assert out["edges"] == []


def test_apply_graph_filter_keeps_valid_edge_and_extra_keys() -> None:
    """Ребро между оставшимися узлами сохраняется, прочие ключи целы."""
    state = GraphFilterState(min_confidence=0.5)
    graph = {
        "nodes": [
            {"id": "n1", "confidence": 0.9},
            {"id": "n2", "confidence": 0.7},
            {"id": "n3", "confidence": 0.1},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
        "meta": {"total": 3},
    }
    out = apply_graph_filter(state, graph)
    assert {n["id"] for n in out["nodes"]} == {"n1", "n2"}
    assert [e["id"] for e in out["edges"]] == ["e1"]
    assert out["meta"] == {"total": 3}


def test_to_query_params_active_fields() -> None:
    """to_query_params сериализует активные поля / active-field serialisation."""
    state = GraphFilterState(node_types=("Material", "Gap"), min_confidence=0.5)
    assert state.to_query_params() == {
        "nodeTypes": "Material,Gap",
        "minConfidence": "0.5",
    }


def test_to_query_params_default_is_empty() -> None:
    """Дефолтное состояние даёт {} / default state serialises to empty dict."""
    assert GraphFilterState().to_query_params() == {}


def test_to_query_params_all_fields() -> None:
    """Все поля активны — полный набор ключей / every active key present."""
    state = GraphFilterState(
        node_types=("Material",),
        sources=("s1", "s2"),
        labs=("labA",),
        min_confidence=0.75,
        verified_only=True,
        date_from="2026-01-01",
    )
    assert state.to_query_params() == {
        "nodeTypes": "Material",
        "sources": "s1,s2",
        "labs": "labA",
        "minConfidence": "0.75",
        "verifiedOnly": "true",
        "dateFrom": "2026-01-01",
    }


def test_as_dict_roundtrip_lists() -> None:
    """as_dict отдаёт все поля списками / as_dict exposes tuples as lists."""
    state = GraphFilterState(node_types=("Material",), sources=("s1",))
    assert state.as_dict() == {
        "node_types": ["Material"],
        "sources": ["s1"],
        "labs": [],
        "min_confidence": 0.0,
        "verified_only": False,
        "date_from": None,
    }


def test_sources_and_labs_and_date_predicate() -> None:
    """Проверка полей sources/labs/date_from в node_matches."""
    state = GraphFilterState(sources=("pubmed",), labs=("mit",), date_from="2026-01-01")
    ok = {"source": "pubmed", "lab": "mit", "date": "2026-06-01"}
    assert node_matches(state, ok) is True
    assert node_matches(state, {**ok, "source": "arxiv"}) is False
    assert node_matches(state, {**ok, "lab": "stanford"}) is False
    assert node_matches(state, {**ok, "date": "2025-12-31"}) is False
    assert node_matches(state, {"source": "pubmed", "lab": "mit"}) is False
