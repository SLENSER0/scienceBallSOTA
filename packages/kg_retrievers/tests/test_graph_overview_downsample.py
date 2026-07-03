"""§17.9 — corpus-overview downsampler over hand-built dict graphs.

Каждый кейс собран вручную и проверяем по определению степени/ties:

- линия a-b-c (deg b=2, a=c=1), max_nodes=2 → оставляем b + один из a/c;
- ребро между уцелевшим и отброшенным узлом убирается;
- при max_nodes >= total граф не меняется (kept==total, dropped==0);
- ties по степени решаются большим ``evidenceCount``;
- дальнейший tie решается меньшим ``id``;
- ``threshold`` == переданный ``max_nodes``;
- пустой граф → kept==0, dropped==0, edges==().
"""

from __future__ import annotations

from kg_retrievers.graph_overview_downsample import (
    OverviewGraph,
    downsample_overview,
)


def _node(node_id: str, evidence: int = 0) -> dict:
    return {"id": node_id, "evidenceCount": evidence}


def _edge(src: str, dst: str) -> dict:
    return {"source": src, "target": dst}


def test_keeps_top_degree_nodes_and_counts() -> None:
    # a-b-c: degree b=2, a=1, c=1. max_nodes=2 keeps b + higher-ranked of a/c.
    graph = {
        "nodes": [_node("a"), _node("b"), _node("c")],
        "edges": [_edge("a", "b"), _edge("b", "c")],
    }
    out = downsample_overview(graph, max_nodes=2)
    kept_ids = {n["id"] for n in out.nodes}
    assert "b" in kept_ids
    assert out.kept_count == 2
    assert out.dropped_count == 1
    assert len(kept_ids) == 2


def test_edge_to_dropped_node_removed() -> None:
    # b (deg 2) and a (deg 1) survive; c is dropped -> edge b-c must go.
    graph = {
        "nodes": [_node("a"), _node("b"), _node("c")],
        "edges": [_edge("a", "b"), _edge("b", "c")],
    }
    out = downsample_overview(graph, max_nodes=2)
    kept_ids = {n["id"] for n in out.nodes}
    for e in out.edges:
        assert e["source"] in kept_ids and e["target"] in kept_ids
    # a and b survive (a beats c by smaller id after equal degree/evidence).
    assert kept_ids == {"a", "b"}
    assert out.edges == ({"source": "a", "target": "b"},)


def test_all_fit_unchanged() -> None:
    graph = {
        "nodes": [_node("a"), _node("b"), _node("c")],
        "edges": [_edge("a", "b"), _edge("b", "c")],
    }
    out = downsample_overview(graph, max_nodes=3)
    assert out.kept_count == 3
    assert out.dropped_count == 0
    assert out.edges == ({"source": "a", "target": "b"}, {"source": "b", "target": "c"})
    # max_nodes strictly greater than total also leaves everything in place.
    out2 = downsample_overview(graph, max_nodes=10)
    assert out2.kept_count == 3
    assert out2.dropped_count == 0


def test_degree_tie_broken_by_evidence() -> None:
    # a and b both degree 0; b has higher evidenceCount -> b kept over a.
    graph = {
        "nodes": [_node("a", evidence=1), _node("b", evidence=9)],
        "edges": [],
    }
    out = downsample_overview(graph, max_nodes=1)
    assert {n["id"] for n in out.nodes} == {"b"}
    assert out.dropped_count == 1


def test_further_tie_broken_by_smaller_id() -> None:
    # equal degree (0) and equal evidence -> smaller id "a" wins over "b".
    graph = {
        "nodes": [_node("b", evidence=5), _node("a", evidence=5)],
        "edges": [],
    }
    out = downsample_overview(graph, max_nodes=1)
    assert {n["id"] for n in out.nodes} == {"a"}


def test_threshold_field_equals_max_nodes() -> None:
    graph = {"nodes": [_node("a")], "edges": []}
    assert downsample_overview(graph, max_nodes=42).threshold == 42
    assert downsample_overview(graph).threshold == 500


def test_empty_graph() -> None:
    out = downsample_overview({"nodes": [], "edges": []}, max_nodes=5)
    assert out.kept_count == 0
    assert out.dropped_count == 0
    assert out.edges == ()
    assert out.nodes == ()


def test_missing_keys_treated_as_empty() -> None:
    out = downsample_overview({}, max_nodes=5)
    assert out.kept_count == 0
    assert out.dropped_count == 0
    assert out.edges == ()


def test_as_dict_camel_case() -> None:
    graph = {
        "nodes": [_node("a"), _node("b"), _node("c")],
        "edges": [_edge("a", "b"), _edge("b", "c")],
    }
    d = downsample_overview(graph, max_nodes=2).as_dict()
    assert set(d) == {"nodes", "edges", "keptCount", "droppedCount", "threshold"}
    assert d["keptCount"] == 2
    assert d["droppedCount"] == 1
    assert d["threshold"] == 2
    assert isinstance(d["nodes"], list)


def test_frozen_result_type() -> None:
    out = downsample_overview({"nodes": [], "edges": []})
    assert isinstance(out, OverviewGraph)
    assert isinstance(out.nodes, tuple)
    assert isinstance(out.edges, tuple)
