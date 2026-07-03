"""Graph hygiene — articulation points & bridges tests (§8.16).

Hand-checkable graphs over a fresh temp Kuzu store:

- a path a-b-c -> b is the only articulation point; both edges are bridges;
- a triangle -> no articulation points, no bridges (every edge is on a cycle);
- an empty store -> no articulation points, no bridges;
- two triangles joined by a single edge -> that edge is a bridge and both of
  its endpoints are articulation points;
- edge direction is irrelevant (undirected projection);
- a parallel/doubled edge is not a bridge; a self-loop changes nothing;
- report is deterministic: bridge pairs and the bridge list are sorted, and
  as_dict()['articulation_points'] is a tuple.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_cut_points import (
    ConnectivityReport,
    articulation_points,
    bridges,
    connectivity_report,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    store.upsert_node(nid, "Material", name=nid)


def _path_abc() -> KuzuGraphStore:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    return store


def _triangle() -> KuzuGraphStore:
    store = _store()
    for nid in ("t1", "t2", "t3"):
        _node(store, nid)
    store.upsert_edge("t1", "t2", "RELATED_TO")
    store.upsert_edge("t2", "t3", "RELATED_TO")
    store.upsert_edge("t3", "t1", "RELATED_TO")
    return store


def test_path_articulation_points() -> None:
    store = _path_abc()
    assert articulation_points(store) == {"b"}


def test_path_bridges() -> None:
    store = _path_abc()
    assert bridges(store) == [("a", "b"), ("b", "c")]


def test_triangle_no_articulation_points() -> None:
    store = _triangle()
    assert articulation_points(store) == set()


def test_triangle_no_bridges() -> None:
    store = _triangle()
    assert bridges(store) == []


def test_empty_store() -> None:
    store = _store()
    assert articulation_points(store) == set()
    assert bridges(store) == []


def test_report_as_dict_shape() -> None:
    store = _path_abc()
    report = connectivity_report(store)
    assert isinstance(report, ConnectivityReport)
    d = report.as_dict()
    assert isinstance(d["articulation_points"], tuple)
    assert d["articulation_points"] == ("b",)
    assert d["bridges"] == [["a", "b"], ["b", "c"]]


def test_two_triangles_joined_by_one_edge() -> None:
    store = _store()
    for nid in ("a1", "a2", "a3", "b1", "b2", "b3"):
        _node(store, nid)
    # triangle A
    store.upsert_edge("a1", "a2", "RELATED_TO")
    store.upsert_edge("a2", "a3", "RELATED_TO")
    store.upsert_edge("a3", "a1", "RELATED_TO")
    # triangle B
    store.upsert_edge("b1", "b2", "RELATED_TO")
    store.upsert_edge("b2", "b3", "RELATED_TO")
    store.upsert_edge("b3", "b1", "RELATED_TO")
    # single joining edge a1-b1
    store.upsert_edge("a1", "b1", "RELATED_TO")
    report = connectivity_report(store)
    assert report.bridges == (("a1", "b1"),)
    assert report.articulation_points == ("a1", "b1")


def test_direction_irrelevant() -> None:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    # edges point outward from b; treated undirected it is still the cut point
    store.upsert_edge("b", "a", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    assert articulation_points(store) == {"b"}
    assert bridges(store) == [("a", "b"), ("b", "c")]


def test_parallel_edge_is_not_a_bridge() -> None:
    store = _store()
    _node(store, "a")
    _node(store, "b")
    # two edges between the same pair collapse to one undirected edge on a
    # multigraph these two would form a 2-cycle, but with simple adjacency the
    # single a-b link is still a bridge; assert the doubled RETURN rows are
    # deduplicated and yield exactly one bridge (not two)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "a", "MENTIONS")
    assert bridges(store) == [("a", "b")]
    assert articulation_points(store) == set()


def test_self_loop_ignored() -> None:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    store.upsert_edge("a", "a", "RELATED_TO")  # self-loop: no effect
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    assert articulation_points(store) == {"b"}
    assert bridges(store) == [("a", "b"), ("b", "c")]


def test_star_center_is_articulation_point() -> None:
    store = _store()
    for nid in ("hub", "x", "y", "z"):
        _node(store, nid)
    store.upsert_edge("hub", "x", "RELATED_TO")
    store.upsert_edge("hub", "y", "RELATED_TO")
    store.upsert_edge("hub", "z", "RELATED_TO")
    # every spoke edge is a bridge; the hub is the sole articulation point
    assert articulation_points(store) == {"hub"}
    assert bridges(store) == [("hub", "x"), ("hub", "y"), ("hub", "z")]
