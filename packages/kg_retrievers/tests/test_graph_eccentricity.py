"""Eccentricity, radius & diameter analytics tests (§8.13).

Hand-checkable graphs over a fresh temp Kuzu store:

- a path a–b–c: eccentricity {'a':2,'b':1,'c':2}, radius 1, diameter 2,
  center ('b',), periphery ('a','c');
- an empty store: radius 0, diameter 0, center (), eccentricity {};
- a disconnected graph (path a–b–c plus an isolated pair d–e): metrics are
  computed on the 3-node component, so diameter == 2;
- as_dict()['eccentricity'] is a plain dict.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_eccentricity import (
    EccentricityReport,
    eccentricity_report,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    store.upsert_node(nid, "Material", name=nid)


def _path_abc(store: KuzuGraphStore) -> None:
    for nid in ("a", "b", "c"):
        _node(store, nid)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")


def test_path_metrics() -> None:
    store = _store()
    _path_abc(store)
    report = eccentricity_report(store)
    assert report.eccentricity == {"a": 2, "b": 1, "c": 2}
    assert report.radius == 1
    assert report.diameter == 2
    assert report.center == ("b",)
    assert report.periphery == ("a", "c")


def test_empty_store() -> None:
    store = _store()
    report = eccentricity_report(store)
    assert report.radius == 0
    assert report.diameter == 0
    assert report.center == ()
    assert report.periphery == ()
    assert report.eccentricity == {}


def test_disconnected_uses_largest_component() -> None:
    store = _store()
    _path_abc(store)
    # An isolated pair d–e (its own 2-node component) must not shrink the metrics.
    for nid in ("d", "e"):
        _node(store, nid)
    store.upsert_edge("d", "e", "RELATED_TO")
    report = eccentricity_report(store)
    # Computed on the 3-node a–b–c component only.
    assert report.diameter == 2
    assert report.radius == 1
    assert set(report.eccentricity) == {"a", "b", "c"}
    assert report.center == ("b",)
    assert report.periphery == ("a", "c")


def test_undirected_treatment() -> None:
    store = _store()
    for nid in ("a", "b", "c"):
        _node(store, nid)
    # Edges point outward from b; treated undirected they still form a path.
    store.upsert_edge("b", "a", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    report = eccentricity_report(store)
    assert report.eccentricity == {"a": 2, "b": 1, "c": 2}
    assert report.center == ("b",)


def test_as_dict_shape() -> None:
    store = _store()
    _path_abc(store)
    report = eccentricity_report(store)
    assert isinstance(report, EccentricityReport)
    d = report.as_dict()
    assert isinstance(d["eccentricity"], dict)
    assert d["eccentricity"] == {"a": 2, "b": 1, "c": 2}
    assert d["radius"] == 1
    assert d["diameter"] == 2
    assert d["center"] == ["b"]
    assert d["periphery"] == ["a", "c"]


def test_empty_as_dict() -> None:
    store = _store()
    report = eccentricity_report(store)
    d = report.as_dict()
    assert d == {
        "eccentricity": {},
        "radius": 0,
        "diameter": 0,
        "center": [],
        "periphery": [],
    }
