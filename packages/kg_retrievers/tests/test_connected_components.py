"""Weakly-connected component analytics tests (§8.13).

Hand-checkable graphs over a fresh temp Kuzu store:

- two disjoint edges a-b, c-d -> 2 components of size 2, no singletons;
- adding an isolated node e -> 3 components, 1 singleton;
- a chain a-b-c over 5 nodes -> largest_fraction == 3/5;
- members within a component are sorted; components[0] is the largest;
- an empty store -> 0 components and largest_fraction 0.0;
- as_dict()['components'] is a list of dicts each carrying 'size'.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.connected_components import (
    Component,
    ComponentReport,
    connected_components,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    store.upsert_node(nid, "Material", name=nid)


def test_two_disjoint_edges() -> None:
    store = _store()
    for nid in ("a", "b", "c", "d"):
        _node(store, nid)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("c", "d", "RELATED_TO")
    report = connected_components(store)
    assert report.n_components == 2
    assert all(c.size == 2 for c in report.components)
    assert report.singletons == 0
    assert report.largest_fraction == 2 / 4


def test_isolated_node_is_singleton() -> None:
    store = _store()
    for nid in ("a", "b", "c", "d", "e"):
        _node(store, nid)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("c", "d", "RELATED_TO")
    report = connected_components(store)
    assert report.n_components == 3
    assert report.singletons == 1
    # the singleton is the isolated node e
    singleton = next(c for c in report.components if c.size == 1)
    assert singleton.members == ("e",)


def test_chain_largest_fraction() -> None:
    store = _store()
    for nid in ("a", "b", "c", "d", "e"):
        _node(store, nid)
    # chain a-b-c is one component of 3; d and e stay isolated
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    report = connected_components(store)
    assert report.n_components == 3
    assert report.largest_fraction == 3 / 5
    assert report.singletons == 2


def test_members_sorted_and_largest_first() -> None:
    store = _store()
    for nid in ("z", "m", "a", "solo"):
        _node(store, nid)
    # component {a, m, z} plus the isolated 'solo'
    store.upsert_edge("z", "m", "RELATED_TO")
    store.upsert_edge("m", "a", "RELATED_TO")
    report = connected_components(store)
    assert report.components[0].size == 3
    assert report.components[0].members == ("a", "m", "z")
    assert report.components[1].members == ("solo",)


def test_undirected_treatment() -> None:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    # edges point outward from b; treated undirected they join all three
    store.upsert_edge("b", "a", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    report = connected_components(store)
    assert report.n_components == 1
    assert report.components[0].members == ("a", "b", "c")
    assert report.largest_fraction == 1.0


def test_empty_store() -> None:
    store = _store()
    report = connected_components(store)
    assert report.n_components == 0
    assert report.components == ()
    assert report.largest_fraction == 0.0
    assert report.singletons == 0


def test_tie_break_by_smallest_member() -> None:
    store = _store()
    for nid in ("a", "b", "x", "y"):
        _node(store, nid)
    store.upsert_edge("x", "y", "RELATED_TO")
    store.upsert_edge("a", "b", "RELATED_TO")
    report = connected_components(store)
    # both size 2 -> ordered by smallest member id: {a,b} before {x,y}
    assert report.components[0].members == ("a", "b")
    assert report.components[1].members == ("x", "y")


def test_as_dict_shape() -> None:
    store = _store()
    _node(store, "a")
    _node(store, "b")
    store.upsert_edge("a", "b", "RELATED_TO")
    report = connected_components(store)
    assert isinstance(report, ComponentReport)
    d = report.as_dict()
    assert isinstance(d["components"], list)
    assert all(isinstance(c, dict) and "size" in c for c in d["components"])
    assert d["n_components"] == 1
    assert d["largest_fraction"] == 1.0


def test_component_as_dict() -> None:
    comp = Component(members=("a", "b"), size=2)
    assert comp.as_dict() == {"members": ["a", "b"], "size": 2}
