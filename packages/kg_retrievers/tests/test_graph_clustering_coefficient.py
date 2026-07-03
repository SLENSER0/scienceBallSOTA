"""Clustering-coefficient & triangle analytics tests (§8.13).

Hand-checkable undirected projections over a fresh temp Kuzu store:

- a triangle t1-t2-t3 -> every local == 1.0, one triangle per node,
  transitivity == 1.0 and average_clustering == 1.0;
- a path a-b-c -> local[b] == 0.0, triangles[b] == 0, transitivity == 0.0;
- an empty store -> transitivity/average 0.0 and empty dicts;
- as_dict()['triangles'] is a plain dict of ints.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_clustering_coefficient import (
    ClusteringResult,
    clustering_report,
    local_clustering,
    triangle_counts,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    store.upsert_node(nid, "Material", name=nid)


def _triangle_store() -> KuzuGraphStore:
    store = _store()
    for nid in ("t1", "t2", "t3"):
        _node(store, nid)
    store.upsert_edge("t1", "t2", "RELATED_TO")
    store.upsert_edge("t2", "t3", "RELATED_TO")
    store.upsert_edge("t3", "t1", "RELATED_TO")
    return store


def _path_store() -> KuzuGraphStore:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    return store


def test_triangle_local_clustering_is_one() -> None:
    store = _triangle_store()
    local = local_clustering(store)
    assert local["t1"] == 1.0
    assert local["t2"] == 1.0
    assert local["t3"] == 1.0


def test_triangle_triangle_counts() -> None:
    store = _triangle_store()
    tri = triangle_counts(store)
    assert tri["t1"] == 1
    assert tri["t2"] == 1
    assert tri["t3"] == 1


def test_triangle_report_transitivity_and_average() -> None:
    store = _triangle_store()
    report = clustering_report(store)
    assert isinstance(report, ClusteringResult)
    assert report.transitivity == 1.0
    assert report.average_clustering == 1.0
    assert report.triangles == {"t1": 1, "t2": 1, "t3": 1}


def test_path_middle_node_has_no_cohesion() -> None:
    store = _path_store()
    assert local_clustering(store)["b"] == 0.0
    assert triangle_counts(store)["b"] == 0


def test_path_transitivity_is_zero() -> None:
    store = _path_store()
    report = clustering_report(store)
    # one open triple centred at b, no closed triples
    assert report.transitivity == 0.0
    # endpoints have degree 1 -> local 0.0 as well
    assert report.local == {"a": 0.0, "b": 0.0, "c": 0.0}


def test_empty_store() -> None:
    store = _store()
    report = clustering_report(store)
    assert report.transitivity == 0.0
    assert report.average_clustering == 0.0
    assert report.local == {}
    assert report.triangles == {}
    assert local_clustering(store) == {}
    assert triangle_counts(store) == {}


def test_as_dict_triangles_is_plain_int_dict() -> None:
    store = _triangle_store()
    d = clustering_report(store).as_dict()
    assert isinstance(d["triangles"], dict)
    assert all(isinstance(v, int) for v in d["triangles"].values())
    assert d["triangles"]["t1"] == 1
    assert d["transitivity"] == 1.0
    assert d["average_clustering"] == 1.0
