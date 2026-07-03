"""Tests for §8.13 node degree distribution and hub detection.

Each test builds a fresh temp store and asserts concrete, hand-checked values.

Star seed (see ``_seed_star``): centre ``c`` with 3 leaves ``l1/l2/l3`` and
directed edges ``c -> l1``, ``c -> l2``, ``c -> l3``.

- centre ``c``: out-degree 3, in-degree 0 -> total degree 3;
- each leaf: in-degree 1, out-degree 0 -> total degree 1;
- histogram: ``{3: 1, 1: 3}``; max_degree 3; mean = 2·3 / 4 = 1.5.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.degree_distribution import DegreeEntry, degree_distribution
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KuzuGraphStore]:
    """Fresh embedded store (schema created, no nodes yet)."""
    s = KuzuGraphStore(str(tmp_path / "g"))
    yield s
    s.close()


def _seed_star(s: KuzuGraphStore) -> None:
    """Centre ``c`` with 3 leaves and 3 directed edges ``c -> leaf`` (see docstring)."""
    s.upsert_node("c", "Material", name="центр")
    s.upsert_node("l1", "Material", name="лист1")
    s.upsert_node("l2", "Material", name="лист2")
    s.upsert_node("l3", "Material", name="лист3")
    s.upsert_edge("c", "l1", "APPLIES_TO")
    s.upsert_edge("c", "l2", "APPLIES_TO")
    s.upsert_edge("c", "l3", "APPLIES_TO")


def test_star_max_degree_and_top_hub(store: KuzuGraphStore) -> None:
    _seed_star(store)
    dist = degree_distribution(store)
    assert dist.max_degree == 3
    assert dist.top_hubs[0].node_id == "c"
    assert dist.top_hubs[0].degree == 3


def test_star_histogram(store: KuzuGraphStore) -> None:
    _seed_star(store)
    dist = degree_distribution(store)
    assert dist.histogram[1] == 3  # three leaves, degree 1 each
    assert dist.histogram[3] == 1  # the centre, degree 3
    assert dist.histogram == {3: 1, 1: 3}


def test_star_mean_degree(store: KuzuGraphStore) -> None:
    _seed_star(store)
    dist = degree_distribution(store)
    assert dist.n_nodes == 4
    assert dist.mean_degree == 1.5  # 2 * 3 edges / 4 nodes


def test_isolated_node_contributes_zero_bucket(store: KuzuGraphStore) -> None:
    _seed_star(store)
    store.upsert_node("iso", "Material", name="одиночка")
    dist = degree_distribution(store)
    assert dist.histogram[0] == 1  # the isolated node
    assert dist.n_nodes == 5  # star's 4 plus the isolated node
    assert dist.max_degree == 3  # unchanged


def test_single_edge_mean_degree(store: KuzuGraphStore) -> None:
    store.upsert_node("a", "Material")
    store.upsert_node("b", "Material")
    store.upsert_edge("a", "b", "APPLIES_TO")
    dist = degree_distribution(store)
    assert dist.mean_degree == 1.0  # 2 * 1 edge / 2 nodes
    assert dist.histogram == {1: 2}


def test_top_k_limits_hubs(store: KuzuGraphStore) -> None:
    _seed_star(store)
    dist = degree_distribution(store, top_k=2)
    assert len(dist.top_hubs) == 2
    assert dist.top_hubs[0].node_id == "c"


def test_top_hubs_sorted_by_degree_then_id(store: KuzuGraphStore) -> None:
    _seed_star(store)
    dist = degree_distribution(store)
    # centre first (degree 3), then the three leaves by id ascending (all degree 1).
    assert [h.node_id for h in dist.top_hubs] == ["c", "l1", "l2", "l3"]
    assert [h.degree for h in dist.top_hubs] == [3, 1, 1, 1]


def test_empty_store(store: KuzuGraphStore) -> None:
    dist = degree_distribution(store)
    assert dist.n_nodes == 0
    assert dist.max_degree == 0
    assert dist.mean_degree == 0.0
    assert dist.histogram == {}
    assert dist.top_hubs == ()


def test_as_dict_histogram_keys_are_ints(store: KuzuGraphStore) -> None:
    _seed_star(store)
    d = degree_distribution(store).as_dict()
    assert all(isinstance(k, int) for k in d["histogram"])
    assert d["histogram"] == {3: 1, 1: 3}
    assert d["max_degree"] == 3
    assert d["top_hubs"][0] == {"node_id": "c", "degree": 3}


def test_entry_as_dict() -> None:
    assert DegreeEntry("x", 5).as_dict() == {"node_id": "x", "degree": 5}


def test_distribution_is_frozen(store: KuzuGraphStore) -> None:
    dist = degree_distribution(store)
    with pytest.raises(FrozenInstanceError):
        dist.max_degree = 99  # type: ignore[misc]
