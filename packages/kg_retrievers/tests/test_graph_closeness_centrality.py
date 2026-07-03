"""Closeness & harmonic centrality over a 3-node path (§3.14 / §12.8).

Hand-checkable facts for the path ``a — b — c`` (three Material nodes chained by
two edges):

- Distances from the middle ``b``: ``d(a)=1, d(c)=1`` → sum 2. Closeness (both
  reachable, n-1 = 2) = ``2 / 2 = 1.0``; harmonic = ``1/1 + 1/1 = 2.0``.
- Distances from an endpoint ``a``: ``d(b)=1, d(c)=2`` → sum 3. Closeness =
  ``2 / 3 = 0.666…``; harmonic = ``1/1 + 1/2 = 1.5``.
- So ``b`` is the single most-central node under either metric.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_closeness_centrality import (
    ClosenessScore,
    closeness_centrality,
    harmonic_centrality,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _path_store() -> KuzuGraphStore:
    """Temp store holding a Material path a — b — c (two undirected edges)."""
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    for nid in ("a", "b", "c"):
        store.upsert_node(nid, "Material", name=nid)
    store.upsert_edge("a", "b", "RELATED_TO")
    store.upsert_edge("b", "c", "RELATED_TO")
    return store


def _empty_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _by_id(rows: list[ClosenessScore]) -> dict[str, ClosenessScore]:
    return {r.entity_id: r for r in rows}


def test_closeness_values_on_path() -> None:
    store = _path_store()
    try:
        rows = _by_id(closeness_centrality(store, top=10))
        assert rows["b"].closeness == 1.0
        assert rows["a"].closeness == pytest.approx(0.6666667)
        # endpoints are symmetric.
        assert rows["c"].closeness == pytest.approx(0.6666667)
    finally:
        store.close()


def test_harmonic_values_on_path() -> None:
    store = _path_store()
    try:
        rows = _by_id(harmonic_centrality(store, top=10))
        assert rows["b"].harmonic == 2.0
        assert rows["a"].harmonic == 1.5
        assert rows["c"].harmonic == 1.5
    finally:
        store.close()


def test_closeness_ranks_middle_first() -> None:
    store = _path_store()
    try:
        ranked = closeness_centrality(store, top=10)
        assert ranked[0].entity_id == "b"
        # endpoints tie on closeness -> broken by id (a before c).
        assert [r.entity_id for r in ranked] == ["b", "a", "c"]
    finally:
        store.close()


def test_harmonic_ranks_middle_first() -> None:
    store = _path_store()
    try:
        ranked = harmonic_centrality(store, top=10)
        assert ranked[0].entity_id == "b"
        assert [r.entity_id for r in ranked] == ["b", "a", "c"]
    finally:
        store.close()


def test_top_zero_returns_empty() -> None:
    store = _path_store()
    try:
        assert harmonic_centrality(store, top=0) == []
        assert closeness_centrality(store, top=0) == []
    finally:
        store.close()


def test_top_limits_result_size() -> None:
    store = _path_store()
    try:
        assert len(closeness_centrality(store, top=1)) == 1
        assert len(harmonic_centrality(store, top=2)) == 2
    finally:
        store.close()


def test_empty_store_is_graceful() -> None:
    store = _empty_store()
    try:
        assert closeness_centrality(store) == []
        assert harmonic_centrality(store) == []
    finally:
        store.close()


def test_as_dict_has_exactly_three_keys() -> None:
    store = _path_store()
    try:
        row = closeness_centrality(store, top=1)[0]
        d = row.as_dict()
        assert set(d) == {"entity_id", "closeness", "harmonic"}
        assert d == {"entity_id": "b", "closeness": 1.0, "harmonic": 2.0}
    finally:
        store.close()
