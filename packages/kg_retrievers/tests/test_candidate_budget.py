"""Tests for §12.1 candidate-budget allocation / truncation (hand-checkable)."""

from __future__ import annotations

from kg_retrievers.candidate_budget import (
    DEFAULT_RERANK_TOP_N,
    DEFAULT_TOP_K,
    BudgetAllocation,
    allocate,
    truncate,
)


def test_allocate_three_sources_default_budget() -> None:
    alloc = allocate(["dense", "sparse", "bm25"])
    assert alloc.per_source == {"dense": 100, "sparse": 100, "bm25": 100}
    assert alloc.total == 300
    assert alloc.rerank_top_n == 50


def test_allocate_defaults_are_100_and_50() -> None:
    assert DEFAULT_TOP_K == 100
    assert DEFAULT_RERANK_TOP_N == 50


def test_allocate_empty_sources() -> None:
    alloc = allocate([])
    assert alloc.per_source == {}
    assert alloc.total == 0
    assert alloc.rerank_top_n == 50


def test_allocate_per_source_keys_equal_input_sources() -> None:
    sources = ["dense", "graph", "bm25"]
    alloc = allocate(sources)
    assert set(alloc.per_source.keys()) == set(sources)


def test_allocate_custom_top_k_and_rerank() -> None:
    alloc = allocate(["dense", "sparse"], top_k=40, rerank_top_n=25)
    assert alloc.per_source == {"dense": 40, "sparse": 40}
    assert alloc.total == 80
    assert alloc.rerank_top_n == 25


def test_allocate_single_source() -> None:
    alloc = allocate(["dense"])
    assert alloc.per_source == {"dense": 100}
    assert alloc.total == 100


def test_truncate_caps_list_to_budget() -> None:
    assert truncate({"dense": [1, 2, 3, 4, 5]}, {"dense": 3}) == {"dense": [1, 2, 3]}


def test_truncate_preserves_order() -> None:
    out = truncate({"dense": ["c", "a", "b", "z"]}, {"dense": 2})
    assert out == {"dense": ["c", "a"]}


def test_truncate_shorter_list_unchanged() -> None:
    out = truncate({"dense": [1, 2]}, {"dense": 5})
    assert out == {"dense": [1, 2]}


def test_truncate_source_absent_from_budget_is_dropped() -> None:
    out = truncate({"dense": [1, 2, 3], "sparse": [9]}, {"dense": 2})
    assert out == {"dense": [1, 2]}
    assert "sparse" not in out


def test_truncate_returns_fresh_lists() -> None:
    original = [1, 2, 3]
    out = truncate({"dense": original}, {"dense": 5})
    assert out["dense"] == [1, 2, 3]
    assert out["dense"] is not original


def test_truncate_empty_input() -> None:
    assert truncate({}, {"dense": 3}) == {}


def test_as_dict_keys_and_values() -> None:
    alloc = allocate(["dense", "sparse", "bm25"])
    d = alloc.as_dict()
    assert set(d.keys()) == {"per_source", "total", "rerank_top_n"}
    assert d["per_source"] == {"dense": 100, "sparse": 100, "bm25": 100}
    assert d["total"] == 300
    assert d["rerank_top_n"] == 50


def test_as_dict_per_source_is_copy() -> None:
    alloc = allocate(["dense"])
    d = alloc.as_dict()
    d["per_source"]["dense"] = 999
    assert alloc.per_source["dense"] == 100


def test_budget_allocation_is_frozen() -> None:
    alloc = BudgetAllocation(per_source={"dense": 100}, total=100, rerank_top_n=50)
    try:
        alloc.total = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("BudgetAllocation must be frozen")
