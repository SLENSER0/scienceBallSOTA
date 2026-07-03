"""Edge-anomaly detection tests (§8.13).

Hand-checkable graphs built per test over a fresh temp Kuzu store:

- a normal ``a -[:HAS_CHUNK]-> b`` edge yields a clean report;
- a ``a -[:CONTRADICTS]-> a`` edge is a self-loop on node ``a``;
- ``a -[:MENTIONS]-> b`` plus ``a -[:ABOUT]-> b`` collapse into one parallel edge
  carrying both types, sorted;
- ``total_edges`` tracks the ``Rel`` row count; a single edge is never parallel;
- the empty store is clean; ``as_dict`` shapes match the spec.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.edge_anomalies import (
    EdgeAnomalyReport,
    ParallelEdge,
    SelfLoop,
    detect_edge_anomalies,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _ab(store: KuzuGraphStore) -> None:
    store.upsert_node("a", "Document", name="a")
    store.upsert_node("b", "Chunk", name="b")


def test_normal_edge_is_clean() -> None:
    store = _store()
    _ab(store)
    store.upsert_edge("a", "b", "HAS_CHUNK")
    report = detect_edge_anomalies(store)
    assert report.ok is True
    assert report.self_loops == ()
    assert report.parallel_edges == ()
    assert report.total_edges == 1


def test_self_loop_reported() -> None:
    store = _store()
    store.upsert_node("a", "Claim", name="a")
    store.upsert_edge("a", "a", "CONTRADICTS")
    report = detect_edge_anomalies(store)
    assert report.self_loops == (SelfLoop(node_id="a", rel_type="CONTRADICTS"),)
    assert report.parallel_edges == ()
    assert report.total_edges == 1
    assert report.ok is False


def test_parallel_edges_reported_sorted() -> None:
    store = _store()
    _ab(store)
    store.upsert_edge("a", "b", "MENTIONS")
    store.upsert_edge("a", "b", "ABOUT")
    report = detect_edge_anomalies(store)
    assert report.self_loops == ()
    assert report.parallel_edges == (
        ParallelEdge(src_id="a", dst_id="b", rel_types=("ABOUT", "MENTIONS")),
    )
    # rel_types are sorted regardless of insertion order
    assert report.parallel_edges[0].rel_types == ("ABOUT", "MENTIONS")
    assert report.total_edges == 2
    assert report.ok is False


def test_single_edge_is_not_parallel() -> None:
    store = _store()
    _ab(store)
    store.upsert_edge("a", "b", "MENTIONS")
    report = detect_edge_anomalies(store)
    assert report.parallel_edges == ()
    assert report.ok is True
    assert report.total_edges == 1


def test_total_edges_matches_rel_rows() -> None:
    store = _store()
    _ab(store)
    store.upsert_node("c", "Chunk", name="c")
    store.upsert_edge("a", "b", "HAS_CHUNK")
    store.upsert_edge("a", "c", "HAS_CHUNK")
    store.upsert_edge("b", "c", "NEXT")
    report = detect_edge_anomalies(store)
    assert report.total_edges == store.counts()["rels"] == 3
    assert report.ok is True


def test_empty_store_is_clean() -> None:
    store = _store()
    report = detect_edge_anomalies(store)
    assert report.ok is True
    assert report.total_edges == 0
    assert report.self_loops == ()
    assert report.parallel_edges == ()


def test_as_dict_shape() -> None:
    store = _store()
    store.upsert_node("a", "Claim", name="a")
    store.upsert_edge("a", "a", "CONTRADICTS")
    report = detect_edge_anomalies(store)
    assert isinstance(report, EdgeAnomalyReport)
    d = report.as_dict()
    assert isinstance(d["self_loops"], list)
    assert d["self_loops"] == [{"node_id": "a", "rel_type": "CONTRADICTS"}]
    assert all("rel_type" in sl for sl in d["self_loops"])
    assert d["parallel_edges"] == []
    assert d["total_edges"] == 1
    assert d["ok"] is False


def test_parallel_as_dict_has_list_rel_types() -> None:
    store = _store()
    _ab(store)
    store.upsert_edge("a", "b", "MENTIONS")
    store.upsert_edge("a", "b", "ABOUT")
    d = detect_edge_anomalies(store).as_dict()
    assert d["parallel_edges"] == [
        {"src_id": "a", "dst_id": "b", "rel_types": ["ABOUT", "MENTIONS"]}
    ]
