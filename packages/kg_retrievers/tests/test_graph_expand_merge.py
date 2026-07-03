"""Tests for §17.8 graph expand/merge — merge an expansion into a base payload.

Проверяем чистое слияние двух §5.3 GraphResponse: дедуп по ``id``, сохранение
раскладки базы (prefer='base'), учёт только по-настоящему новых узлов/рёбер.
"""

from __future__ import annotations

from kg_retrievers.graph_expand_merge import MergedGraph, merge_graph


def _node(node_id: str, **props: object) -> dict[str, object]:
    return {"id": node_id, "label": "Node", **props}


def _edge(edge_id: str, source: str, target: str, **props: object) -> dict[str, object]:
    return {"id": edge_id, "source": source, "target": target, **props}


def test_shared_node_keeps_base_dict_with_prefer_base() -> None:
    # id 'a' in both — must appear once and equal the *base* dict (layout preserved).
    base = {"nodes": [_node("a", x=10.0, y=20.0)], "edges": []}
    expansion = {"nodes": [_node("a", x=0.0, y=0.0, extra="new")], "edges": []}

    merged = merge_graph(base, expansion)

    a_nodes = [n for n in merged.nodes if n["id"] == "a"]
    assert len(a_nodes) == 1
    assert a_nodes[0] == _node("a", x=10.0, y=20.0)
    assert "a" not in merged.added_node_ids


def test_expansion_only_node_is_appended_and_recorded() -> None:
    base = {"nodes": [_node("a")], "edges": []}
    expansion = {"nodes": [_node("a"), _node("b")], "edges": []}

    merged = merge_graph(base, expansion)

    ids = [n["id"] for n in merged.nodes]
    assert ids == ["a", "b"]  # base 'a' before newly added 'b'
    assert merged.added_node_ids == ("b",)


def test_base_nodes_always_before_added() -> None:
    base = {"nodes": [_node("a"), _node("b")], "edges": []}
    expansion = {"nodes": [_node("c"), _node("d")], "edges": []}

    merged = merge_graph(base, expansion)

    ids = [n["id"] for n in merged.nodes]
    assert ids[:2] == ["a", "b"]  # base first
    assert ids[2:] == ["c", "d"]  # then added, in expansion order
    assert merged.added_node_ids == ("c", "d")


def test_shared_edge_deduped_to_one() -> None:
    base = {"nodes": [], "edges": [_edge("e1", "a", "b", confidence=0.9)]}
    expansion = {"nodes": [], "edges": [_edge("e1", "a", "b", confidence=0.1)]}

    merged = merge_graph(base, expansion)

    e1 = [e for e in merged.edges if e["id"] == "e1"]
    assert len(e1) == 1
    assert e1[0]["confidence"] == 0.9  # base copy kept
    assert merged.added_edge_ids == ()


def test_added_edge_ids_only_truly_new() -> None:
    base = {"nodes": [], "edges": [_edge("e1", "a", "b")]}
    expansion = {
        "nodes": [],
        "edges": [_edge("e1", "a", "b"), _edge("e2", "b", "c")],
    }

    merged = merge_graph(base, expansion)

    edge_ids = [e["id"] for e in merged.edges]
    assert edge_ids == ["e1", "e2"]
    assert merged.added_edge_ids == ("e2",)


def test_prefer_expansion_overwrites_shared_node() -> None:
    base = {"nodes": [_node("a", x=10.0, y=20.0)], "edges": []}
    expansion = {"nodes": [_node("a", x=0.0, y=0.0, extra="new")], "edges": []}

    merged = merge_graph(base, expansion, prefer="expansion")

    a_nodes = [n for n in merged.nodes if n["id"] == "a"]
    assert len(a_nodes) == 1
    assert a_nodes[0] == _node("a", x=0.0, y=0.0, extra="new")
    # still not "added" — the id already existed in base
    assert "a" not in merged.added_node_ids


def test_empty_expansion_leaves_base_unchanged() -> None:
    base = {
        "nodes": [_node("a"), _node("b")],
        "edges": [_edge("e1", "a", "b")],
    }
    expansion = {"nodes": [], "edges": []}

    merged = merge_graph(base, expansion)

    assert [n["id"] for n in merged.nodes] == ["a", "b"]
    assert [e["id"] for e in merged.edges] == ["e1"]
    assert merged.added_node_ids == ()
    assert merged.added_edge_ids == ()


def test_as_dict_exposes_camelcase_keys() -> None:
    base = {"nodes": [_node("a")], "edges": [_edge("e1", "a", "b")]}
    expansion = {"nodes": [_node("b")], "edges": [_edge("e2", "b", "c")]}

    merged = merge_graph(base, expansion)
    payload = merged.as_dict()

    assert set(payload) == {"nodes", "edges", "addedNodeIds", "addedEdgeIds"}
    assert [n["id"] for n in payload["nodes"]] == ["a", "b"]
    assert [e["id"] for e in payload["edges"]] == ["e1", "e2"]
    assert payload["addedNodeIds"] == ["b"]
    assert payload["addedEdgeIds"] == ["e2"]


def test_result_is_frozen_mergedgraph() -> None:
    merged = merge_graph({"nodes": [], "edges": []}, {"nodes": [], "edges": []})
    assert isinstance(merged, MergedGraph)
    assert merged.nodes == ()
    assert merged.edges == ()
    # as_dict copies: mutating the copy does not touch source dicts.
    base_node = _node("a", x=1.0)
    merged2 = merge_graph({"nodes": [base_node], "edges": []}, {"nodes": [], "edges": []})
    merged2.as_dict()["nodes"][0]["x"] = 999.0
    assert base_node["x"] == 1.0


def test_missing_keys_read_as_empty() -> None:
    merged = merge_graph({}, {})
    assert merged.nodes == ()
    assert merged.edges == ()
    assert merged.added_node_ids == ()
    assert merged.added_edge_ids == ()


def test_invalid_prefer_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        merge_graph({"nodes": [], "edges": []}, {"nodes": [], "edges": []}, prefer="bogus")
