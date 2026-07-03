"""k-core decomposition tests (§8.13 analytics).

Hand-checkable graphs over a fresh temp Kuzu store:

- a triangle t1,t2,t3 (all mutually connected) forms a 2-core, so each has
  core number 2; a pendant p attached only to t1 has core number 1;
- the max core is 2, achieved by exactly {t1,t2,t3};
- k_core_members(store,2) == {t1,t2,t3}; k_core_members(store,3) == set();
- an empty store gives max_core 0 and no max-core members;
- as_dict()['core_numbers'] is a plain dict.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_kcore import (
    KCoreResult,
    core_numbers,
    k_core_members,
    kcore_report,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    store.upsert_node(nid, "Material", name=nid)


def _triangle_with_pendant() -> KuzuGraphStore:
    """Triangle t1-t2-t3 (fully connected) plus pendant p attached to t1 only."""
    store = _store()
    for nid in ("t1", "t2", "t3", "p"):
        _node(store, nid)
    store.upsert_edge("t1", "t2", "RELATED_TO")
    store.upsert_edge("t2", "t3", "RELATED_TO")
    store.upsert_edge("t3", "t1", "RELATED_TO")
    store.upsert_edge("t1", "p", "RELATED_TO")
    return store


def test_triangle_core_numbers() -> None:
    store = _triangle_with_pendant()
    numbers = core_numbers(store)
    assert numbers["t1"] == 2
    assert numbers["t2"] == 2
    assert numbers["t3"] == 2
    assert numbers["p"] == 1


def test_max_core_is_two() -> None:
    store = _triangle_with_pendant()
    report = kcore_report(store)
    assert report.max_core == 2
    assert set(report.max_core_members) == {"t1", "t2", "t3"}


def test_max_core_members_sorted() -> None:
    store = _triangle_with_pendant()
    # members are returned sorted by id for determinism
    assert kcore_report(store).max_core_members == ("t1", "t2", "t3")


def test_k_core_members_by_level() -> None:
    store = _triangle_with_pendant()
    assert k_core_members(store, 2) == {"t1", "t2", "t3"}
    # the pendant joins the 1-core; the whole graph is in the 1-core
    assert k_core_members(store, 1) == {"t1", "t2", "t3", "p"}
    assert k_core_members(store, 3) == set()


def test_empty_store() -> None:
    store = _store()
    report = kcore_report(store)
    assert report.max_core == 0
    assert report.max_core_members == ()
    assert report.core_numbers == {}
    assert core_numbers(store) == {}
    assert k_core_members(store, 1) == set()


def test_undirected_projection() -> None:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    # directed edges out of b; treated undirected they form a path a-b-c
    store.upsert_edge("b", "a", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    numbers = core_numbers(store)
    # a path graph is a pure 1-core: every node has core number 1
    assert numbers == {"a": 1, "b": 1, "c": 1}
    assert kcore_report(store).max_core == 1


def test_self_loop_dropped() -> None:
    store = _store()
    _node(store, "x")
    _node(store, "y")
    store.upsert_edge("x", "x", "RELATED_TO")  # self-loop
    store.upsert_edge("x", "y", "RELATED_TO")
    # with the self-loop dropped, x-y is a single edge -> both in the 1-core
    numbers = core_numbers(store)
    assert numbers == {"x": 1, "y": 1}


def test_as_dict_shape() -> None:
    store = _triangle_with_pendant()
    report = kcore_report(store)
    assert isinstance(report, KCoreResult)
    d = report.as_dict()
    assert isinstance(d["core_numbers"], dict)
    assert d["core_numbers"]["t1"] == 2
    assert d["max_core"] == 2
    assert isinstance(d["max_core_members"], list)
    assert set(d["max_core_members"]) == {"t1", "t2", "t3"}
