"""Orphan-node detection tests (§8.16).

Hand-checkable graph built per test over a fresh temp Kuzu store:

- an isolated node (no edges) is an orphan;
- a node with any edge (in or out) is not;
- the label filter restricts which orphans are reported;
- the report counts orphans and breaks them down by label.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.orphan_nodes import OrphanReport, find_orphans, orphan_report


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def test_isolated_node_is_orphan() -> None:
    store = _store()
    store.upsert_node("solo", "Material", name="lonely")
    assert find_orphans(store) == ["solo"]


def test_connected_nodes_not_orphan() -> None:
    store = _store()
    store.upsert_node("a", "Material", name="a")
    store.upsert_node("b", "Material", name="b")
    store.upsert_edge("a", "b", "RELATED_TO")
    # both endpoints of the single edge are linked -> no orphans
    assert find_orphans(store) == []


def test_mixed_graph_finds_only_isolated() -> None:
    store = _store()
    store.upsert_node("a", "Material", name="a")
    store.upsert_node("b", "Material", name="b")
    store.upsert_node("island", "Observation", name="island")
    store.upsert_edge("a", "b", "RELATED_TO")
    assert find_orphans(store) == ["island"]


def test_label_filter() -> None:
    store = _store()
    store.upsert_node("m1", "Material", name="m1")
    store.upsert_node("o1", "Observation", name="o1")
    # both are isolated, but only Material is requested
    assert find_orphans(store, labels={"Material"}) == ["m1"]
    assert find_orphans(store, labels={"Observation"}) == ["o1"]
    assert find_orphans(store, labels={"Document"}) == []


def test_report_by_label() -> None:
    store = _store()
    store.upsert_node("m1", "Material", name="m1")
    store.upsert_node("m2", "Material", name="m2")
    store.upsert_node("o1", "Observation", name="o1")
    store.upsert_node("linked1", "Material", name="l1")
    store.upsert_node("linked2", "Material", name="l2")
    store.upsert_edge("linked1", "linked2", "RELATED_TO")
    report = orphan_report(store)
    assert report.total_orphans == 3
    assert report.by_label == {"Material": 2, "Observation": 1}


def test_empty_store_has_no_orphans() -> None:
    store = _store()
    assert find_orphans(store) == []
    report = orphan_report(store)
    assert report.total_orphans == 0
    assert report.by_label == {}


def test_report_as_dict() -> None:
    store = _store()
    store.upsert_node("x", "Gap", name="x")
    report = orphan_report(store)
    assert isinstance(report, OrphanReport)
    assert report.as_dict() == {"total_orphans": 1, "by_label": {"Gap": 1}}


def test_self_loop_node_is_not_orphan() -> None:
    store = _store()
    store.upsert_node("loop", "Material", name="loop")
    store.upsert_edge("loop", "loop", "RELATED_TO")
    # a self-loop still makes the node an edge endpoint -> not isolated
    assert find_orphans(store) == []
