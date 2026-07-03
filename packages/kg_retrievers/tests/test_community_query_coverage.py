"""Tests for query-entity coverage per community (§11.7/§11.8)."""

from __future__ import annotations

from kg_retrievers.community_query_coverage import (
    CommunityCoverage,
    best_community,
    coverage_by_community,
)


def test_full_coverage_is_one() -> None:
    """A community containing all query entities has coverage 1.0."""
    members = {(0, 0): ["a", "b", "c"]}
    result = coverage_by_community(["a", "b"], members)
    assert len(result) == 1
    assert result[0].coverage == 1.0
    assert result[0].covered == ("a", "b")
    assert result[0].size == 3


def test_partial_coverage_is_half() -> None:
    """A community with 1 of 2 query entities has coverage 0.5."""
    members = {(7, 0): ["a", "x", "y"]}
    result = coverage_by_community(["a", "b"], members)
    assert len(result) == 1
    assert result[0].coverage == 0.5
    assert result[0].covered == ("a",)
    assert result[0].community_id == 7


def test_no_overlap_absent() -> None:
    """A community with no query-entity overlap is absent from the result."""
    members = {(0, 0): ["a"], (1, 0): ["p", "q"]}
    result = coverage_by_community(["a", "b"], members)
    ids = {c.community_id for c in result}
    assert ids == {0}


def test_sorted_highest_coverage_first() -> None:
    """Results sort by highest coverage first."""
    members = {
        (0, 0): ["a"],
        (1, 0): ["a", "b", "c"],
        (2, 0): ["b"],
    }
    result = coverage_by_community(["a", "b", "c"], members)
    coverages = [c.coverage for c in result]
    assert coverages == sorted(coverages, reverse=True)
    assert result[0].community_id == 1
    assert result[0].coverage == 1.0


def test_tie_breaks_by_lower_community_id() -> None:
    """A coverage tie breaks by lower community_id."""
    members = {
        (5, 0): ["a"],
        (2, 0): ["b"],
        (9, 0): ["a", "b"],
    }
    result = coverage_by_community(["a", "b"], members)
    # (9,0) has full coverage; (2,0) and (5,0) tie at 0.5 -> 2 before 5.
    assert [c.community_id for c in result] == [9, 2, 5]


def test_empty_query_returns_empty() -> None:
    """Empty query_entities returns []."""
    members = {(0, 0): ["a", "b"]}
    assert coverage_by_community([], members) == []


def test_level_filter_drops_other_levels() -> None:
    """The level filter drops communities at other levels."""
    members = {
        (0, 0): ["a", "b"],
        (0, 1): ["a", "b"],
        (1, 1): ["a"],
    }
    result = coverage_by_community(["a", "b"], members, level=1)
    assert {c.community_id for c in result} == {0, 1}
    assert all(c.level == 1 for c in result)


def test_size_equals_member_count() -> None:
    """size equals len(members)."""
    members = {(3, 0): ["a", "b", "c", "d"]}
    result = coverage_by_community(["a"], members)
    assert result[0].size == 4


def test_best_community_returns_top_entry() -> None:
    """best_community returns the highest-coverage entry."""
    members = {
        (0, 0): ["a"],
        (1, 0): ["a", "b"],
    }
    best = best_community(["a", "b"], members)
    assert best is not None
    assert best.community_id == 1
    assert best.coverage == 1.0


def test_best_community_none_without_overlap() -> None:
    """best_community returns None when no community overlaps the query."""
    members = {(0, 0): ["x"], (1, 0): ["y"]}
    assert best_community(["a", "b"], members) is None


def test_best_community_respects_level() -> None:
    """best_community honours the level filter."""
    members = {
        (0, 0): ["a", "b"],
        (1, 1): ["a"],
    }
    best = best_community(["a", "b"], members, level=1)
    assert best is not None
    assert best.community_id == 1
    assert best.level == 1
    assert best.coverage == 0.5


def test_as_dict_shape() -> None:
    """as_dict() exposes a JSON-friendly mapping."""
    cov = CommunityCoverage(
        community_id=4,
        level=2,
        covered=("a", "b"),
        coverage=1.0,
        size=3,
    )
    assert cov.as_dict() == {
        "community_id": 4,
        "level": 2,
        "covered": ["a", "b"],
        "coverage": 1.0,
        "size": 3,
    }
