"""Bounded BFS layers over a temp KuzuGraphStore (§8.12).

Seed path graph (edges stored directed, traversed undirected):

    a -> b -> c -> d

plus an isolated node ``iso`` (no edges) to exercise the seed-exists-but-no-edges
case. All distances/layers below are hand-computed against this fixed shape.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_bfs_layers import BfsLayers, bfs_layers
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _seed(s)
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    for nid in ("a", "b", "c", "d", "iso"):
        s.upsert_node(nid, "Material", name=nid)
    s.upsert_edge("a", "b", "CONNECTED")
    s.upsert_edge("b", "c", "CONNECTED")
    s.upsert_edge("c", "d", "CONNECTED")


def test_full_path_distances(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "a", max_depth=3)
    assert res.distances == {"a": 0, "b": 1, "c": 2, "d": 3}
    assert res.reached == frozenset({"a", "b", "c", "d"})


def test_layers_ordering(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "a", max_depth=3)
    assert res.layers[0] == ("a",)
    assert res.layers[1] == ("b",)
    assert res.layers[2] == ("c",)
    assert res.layers[3] == ("d",)


def test_depth_bound_stops_early(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "a", max_depth=1)
    assert res.reached == frozenset({"a", "b"})
    assert "c" not in res.distances
    assert res.distances == {"a": 0, "b": 1}


def test_unknown_seed_is_empty(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "unknown")
    assert res.distances == {}
    assert res.reached == frozenset()
    assert res.layers == ()


def test_seed_always_reached_when_present(store: KuzuGraphStore) -> None:
    # Isolated node: exists but has no edges — reached must still hold the seed.
    res = bfs_layers(store, "iso", max_depth=3)
    assert res.reached == frozenset({"iso"})
    assert res.distances == {"iso": 0}
    assert res.layers == (("iso",),)


def test_undirected_from_middle(store: KuzuGraphStore) -> None:
    # Starting at 'c', undirected traversal reaches both directions.
    res = bfs_layers(store, "c", max_depth=3)
    assert res.distances == {"c": 0, "b": 1, "d": 1, "a": 2}
    assert res.layers[1] == ("b", "d")


def test_as_dict_shape(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "a", max_depth=3)
    payload = res.as_dict()
    dists = payload["distances"]
    assert isinstance(dists, dict)
    assert dists == {"a": 0, "b": 1, "c": 2, "d": 3}
    assert all(isinstance(v, int) for v in dists.values())
    assert payload["layers"] == [["a"], ["b"], ["c"], ["d"]]
    assert payload["seed"] == "a"
    assert payload["reached"] == ["a", "b", "c", "d"]


def test_max_depth_zero_keeps_only_seed(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "a", max_depth=0)
    assert res.distances == {"a": 0}
    assert res.layers == (("a",),)


def test_result_is_frozen(store: KuzuGraphStore) -> None:
    res = bfs_layers(store, "a")
    assert isinstance(res, BfsLayers)
    with pytest.raises(AttributeError):
        res.seed = "x"  # type: ignore[misc]
