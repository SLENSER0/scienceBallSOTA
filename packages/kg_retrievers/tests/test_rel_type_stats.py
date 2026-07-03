"""Relationship-type frequency stats over a temp Kuzu store (§8.15).

Hand-built graph (five nodes n1..n5):
- ``USES``:    n1->n2, n3->n4, n5->n1  (3 edges)
- ``FIXES``:   n2->n3, n4->n5          (2 edges)
- ``BLOCKS``:  n1->n3                   (1 edge)
Total = 6 edges. Expected ranking (count desc, type asc):
``USES``(3), ``FIXES``(2), ``BLOCKS``(1).
"""

from __future__ import annotations

import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.rel_type_stats import RelTypeStats, rel_type_stats


def _build(store: KuzuGraphStore) -> None:
    for i in range(1, 6):
        store.upsert_node(f"n{i}", "Entity", name=f"node {i}")
    store.upsert_edge("n1", "n2", "USES")
    store.upsert_edge("n3", "n4", "USES")
    store.upsert_edge("n5", "n1", "USES")
    store.upsert_edge("n2", "n3", "FIXES")
    store.upsert_edge("n4", "n5", "FIXES")
    store.upsert_edge("n1", "n3", "BLOCKS")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def test_counts_by_type(store: KuzuGraphStore) -> None:
    stats = rel_type_stats(store)
    assert stats.by_type == {"USES": 3, "FIXES": 2, "BLOCKS": 1}


def test_total(store: KuzuGraphStore) -> None:
    stats = rel_type_stats(store)
    assert stats.total == 6


def test_top_sorted(store: KuzuGraphStore) -> None:
    stats = rel_type_stats(store)
    assert stats.top == (("USES", 3), ("FIXES", 2), ("BLOCKS", 1))
    assert stats.top_type == "USES"


def test_empty_store_zeros(empty_store: KuzuGraphStore) -> None:
    stats = rel_type_stats(empty_store)
    assert stats.by_type == {}
    assert stats.total == 0
    assert stats.top == ()
    assert stats.top_type is None


def test_as_dict(store: KuzuGraphStore) -> None:
    stats = rel_type_stats(store)
    assert stats.as_dict() == {
        "by_type": {"USES": 3, "FIXES": 2, "BLOCKS": 1},
        "total": 6,
        "top": [["USES", 3], ["FIXES", 2], ["BLOCKS", 1]],
    }


def test_single_type(empty_store: KuzuGraphStore) -> None:
    empty_store.upsert_node("a", "Entity", name="a")
    empty_store.upsert_node("b", "Entity", name="b")
    empty_store.upsert_node("c", "Entity", name="c")
    empty_store.upsert_edge("a", "b", "USES")
    empty_store.upsert_edge("b", "c", "USES")
    stats = rel_type_stats(empty_store)
    assert stats.by_type == {"USES": 2}
    assert stats.total == 2
    assert stats.top == (("USES", 2),)
    assert stats.top_type == "USES"


def test_tie_break_by_type_name(empty_store: KuzuGraphStore) -> None:
    empty_store.upsert_node("a", "Entity", name="a")
    empty_store.upsert_node("b", "Entity", name="b")
    # one edge of each type -> tie on count, ordered alphabetically by type
    empty_store.upsert_edge("a", "b", "ZED")
    empty_store.upsert_edge("b", "a", "ALPHA")
    stats = rel_type_stats(empty_store)
    assert stats.top == (("ALPHA", 1), ("ZED", 1))


def test_frozen_dataclass() -> None:
    stats = RelTypeStats(by_type={"USES": 1}, total=1, top=(("USES", 1),))
    with pytest.raises(FrozenInstanceError):
        stats.total = 2  # type: ignore[misc]
