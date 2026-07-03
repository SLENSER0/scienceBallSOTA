"""Tests for the Graph Explorer category-toggle filter (§17.8 / §17.16).

Проверяем чистую функцию ``apply_category_filter`` над §5.3 GraphResponse dict:
скрытие типов узлов/рёбер, удаление повисших рёбер, счётчики и JSON-сериализацию.
"""

from __future__ import annotations

import json

from kg_retrievers.graph_category_filter import (
    FilteredGraph,
    apply_category_filter,
    apply_category_filter_json,
)


def _payload() -> dict:
    """Two Material nodes + one Paper node, with edges §5.3."""
    return {
        "nodes": [
            {"id": "m1", "type": "Material", "label": "Al-6061"},
            {"id": "m2", "type": "Material", "label": "Ti-64"},
            {"id": "p1", "type": "Paper", "label": "Smith 2020"},
        ],
        "edges": [
            {"id": "e1", "source": "m1", "target": "m2", "type": "SIMILAR"},
            {"id": "e2", "source": "m1", "target": "p1", "type": "CITED_IN"},
            {"id": "e3", "source": "m2", "target": "m1", "type": "INFERRED"},
        ],
    }


def test_no_hidden_sets_is_identity_with_zero_counts() -> None:
    result = apply_category_filter(_payload())
    assert len(result.nodes) == 3
    assert len(result.edges) == 3
    assert result.hidden_node_count == 0
    assert result.hidden_edge_count == 0
    # Kept elements are the same dicts, unchanged.
    assert [n["id"] for n in result.nodes] == ["m1", "m2", "p1"]
    assert [e["id"] for e in result.edges] == ["e1", "e2", "e3"]


def test_hiding_paper_drops_node_and_incident_edge() -> None:
    result = apply_category_filter(_payload(), hidden_node_types={"Paper"})
    # 2 Material survive, Paper removed.
    assert len(result.nodes) == 2
    assert {n["type"] for n in result.nodes} == {"Material"}
    assert result.hidden_node_count == 1
    # e2 touched the removed Paper -> dropped and counted.
    assert "e2" not in {e["id"] for e in result.edges}
    assert result.hidden_edge_count == 1


def test_hiding_edge_type_keeps_nodes() -> None:
    result = apply_category_filter(_payload(), hidden_edge_types={"INFERRED"})
    assert len(result.nodes) == 3
    assert result.hidden_node_count == 0
    assert "e3" not in {e["id"] for e in result.edges}
    assert len(result.edges) == 2
    assert result.hidden_edge_count == 1


def test_hiding_absent_node_type_is_no_change() -> None:
    result = apply_category_filter(_payload(), hidden_node_types={"Equipment"})
    assert len(result.nodes) == 3
    assert len(result.edges) == 3
    assert result.hidden_node_count == 0
    assert result.hidden_edge_count == 0


def test_orphan_edge_dropped_even_when_type_visible() -> None:
    # e2 type CITED_IN is NOT hidden, but its Paper endpoint is removed.
    result = apply_category_filter(_payload(), hidden_node_types={"Paper"})
    surviving_ids = {n["id"] for n in result.nodes}
    for edge in result.edges:
        assert edge["source"] in surviving_ids
        assert edge["target"] in surviving_ids
    assert "e2" not in {e["id"] for e in result.edges}


def test_kept_edges_only_reference_surviving_nodes() -> None:
    result = apply_category_filter(
        _payload(),
        hidden_node_types={"Material"},
    )
    # All Materials gone -> only Paper survives, and every edge touches a Material.
    assert {n["id"] for n in result.nodes} == {"p1"}
    assert result.nodes[0]["type"] == "Paper"
    assert len(result.edges) == 0
    assert result.hidden_node_count == 2
    assert result.hidden_edge_count == 3


def test_as_dict_shape_and_hidden_edge_count_and_json() -> None:
    result = apply_category_filter(_payload(), hidden_node_types={"Paper"})
    d = result.as_dict()
    assert set(d) == {"nodes", "edges", "hiddenNodeCount", "hiddenEdgeCount"}
    # hiddenEdgeCount == number of edges removed for any reason (orphan e2).
    original_edge_ids = {"e1", "e2", "e3"}
    kept_edge_ids = {e["id"] for e in d["edges"]}
    assert d["hiddenEdgeCount"] == len(original_edge_ids - kept_edge_ids) == 1
    assert d["hiddenNodeCount"] == 1
    # json.dumps succeeds and round-trips.
    encoded = json.dumps(d)
    assert json.loads(encoded)["hiddenEdgeCount"] == 1


def test_frozen_dataclass_and_json_helper() -> None:
    result = apply_category_filter(_payload())
    assert isinstance(result, FilteredGraph)
    # Frozen -> immutable.
    try:
        result.hidden_node_count = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("FilteredGraph must be frozen")
    # json convenience helper matches as_dict().
    assert (
        json.loads(apply_category_filter_json(_payload()))
        == apply_category_filter(_payload()).as_dict()
    )


def test_combined_node_and_edge_hiding_counts() -> None:
    result = apply_category_filter(
        _payload(),
        hidden_node_types={"Paper"},
        hidden_edge_types={"INFERRED"},
    )
    # Nodes: Paper gone (1 hidden). Edges: e2 orphaned, e3 INFERRED -> 2 hidden.
    assert result.hidden_node_count == 1
    assert {e["id"] for e in result.edges} == {"e1"}
    assert result.hidden_edge_count == 2
