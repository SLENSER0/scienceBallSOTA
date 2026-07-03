"""Tests for §8.12 shared-neighbor co-occurrence projection.

Each test builds a fresh temp store. Base material/measurement graph:

    mx -MEASURED-> m1     my -MEASURED-> m1      (mx,my share m1)
    mx -MEASURED-> m2     mz -MEASURED-> m2      (mx,mz share m2)

Hand-checked co-occurrence over label ``Material`` (ids sort mx < my < mz):

- (mx, my): shared 1 via ('m1',);
- (mx, mz): shared 1 via ('m2',);
- (my, mz): no common neighbour -> no edge.

Adding a second shared measurement m3 to mx and my raises (mx, my) to
shared 2 via ('m1', 'm3').
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.graph_cooccurrence import (
    CooccurrenceEdge,
    shared_neighbor_cooccurrence,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KuzuGraphStore]:
    """Fresh embedded store (schema created, no nodes yet)."""
    s = KuzuGraphStore(str(tmp_path / "g"))
    yield s
    s.close()


def _seed_base(s: KuzuGraphStore) -> None:
    """Three materials + two measurements bridging them (see module docstring)."""
    s.upsert_node("mx", "Material", name="Никель")
    s.upsert_node("my", "Material", name="Медь")
    s.upsert_node("mz", "Material", name="Цинк")
    s.upsert_node("m1", "Measurement", name="current density")
    s.upsert_node("m2", "Measurement", name="hardness")
    s.upsert_edge("mx", "m1", "MEASURED", confidence=0.9)
    s.upsert_edge("my", "m1", "MEASURED", confidence=0.9)
    s.upsert_edge("mx", "m2", "MEASURED", confidence=0.8)
    s.upsert_edge("mz", "m2", "MEASURED", confidence=0.8)


def _add_m3(s: KuzuGraphStore) -> None:
    """A second shared measurement linking mx and my."""
    s.upsert_node("m3", "Measurement", name="corrosion rate")
    s.upsert_edge("mx", "m3", "MEASURED", confidence=0.7)
    s.upsert_edge("my", "m3", "MEASURED", confidence=0.7)


def _find(edges: list[CooccurrenceEdge], a: str, b: str) -> CooccurrenceEdge | None:
    for e in edges:
        if e.a == a and e.b == b:
            return e
    return None


def test_shared_edge_mx_my_via_m1(store: KuzuGraphStore) -> None:
    _seed_base(store)
    edges = shared_neighbor_cooccurrence(store, "Material")
    e = _find(edges, "mx", "my")
    assert e is not None
    assert e.shared == 1
    assert e.via == ("m1",)


def test_shared_edge_mx_mz_via_m2(store: KuzuGraphStore) -> None:
    _seed_base(store)
    e = _find(shared_neighbor_cooccurrence(store, "Material"), "mx", "mz")
    assert e is not None
    assert e.shared == 1
    assert e.via == ("m2",)


def test_adding_m3_raises_shared_to_two(store: KuzuGraphStore) -> None:
    _seed_base(store)
    _add_m3(store)
    e = _find(shared_neighbor_cooccurrence(store, "Material"), "mx", "my")
    assert e is not None
    assert e.shared == 2
    assert e.via == ("m1", "m3")


def test_every_edge_a_lt_b(store: KuzuGraphStore) -> None:
    _seed_base(store)
    _add_m3(store)
    edges = shared_neighbor_cooccurrence(store, "Material")
    assert edges  # non-empty
    for e in edges:
        assert e.a < e.b


def test_pair_sharing_nothing_has_no_edge(store: KuzuGraphStore) -> None:
    _seed_base(store)
    # my (->m1) and mz (->m2) have no common neighbour.
    edges = shared_neighbor_cooccurrence(store, "Material")
    assert _find(edges, "my", "mz") is None


def test_never_returns_self_pair(store: KuzuGraphStore) -> None:
    _seed_base(store)
    _add_m3(store)
    for e in shared_neighbor_cooccurrence(store, "Material"):
        assert e.a != e.b


def test_empty_store_returns_empty(store: KuzuGraphStore) -> None:
    assert shared_neighbor_cooccurrence(store, "Material") == []


def test_ranked_by_shared_desc_then_pair(store: KuzuGraphStore) -> None:
    _seed_base(store)
    _add_m3(store)
    edges = shared_neighbor_cooccurrence(store, "Material")
    keys = [(-e.shared, e.a, e.b) for e in edges]
    assert keys == sorted(keys)
    # (mx,my) shared 2 outranks (mx,mz) shared 1.
    assert (edges[0].a, edges[0].b) == ("mx", "my")


def test_as_dict_via_is_tuple(store: KuzuGraphStore) -> None:
    _seed_base(store)
    e = _find(shared_neighbor_cooccurrence(store, "Material"), "mx", "my")
    assert e is not None
    d = e.as_dict()
    assert type(d["via"]) is tuple
    assert d == {"a": "mx", "b": "my", "shared": 1, "via": ("m1",)}


def test_as_dict_via_sorted(store: KuzuGraphStore) -> None:
    e = CooccurrenceEdge(a="mx", b="my", shared=2, via=("m3", "m1"))
    assert e.as_dict()["via"] == ("m1", "m3")


def test_edge_is_frozen() -> None:
    e = CooccurrenceEdge(a="mx", b="my", shared=1, via=("m1",))
    with pytest.raises(FrozenInstanceError):
        e.shared = 99  # type: ignore[misc]
