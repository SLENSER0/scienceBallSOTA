"""Tests for §11.16 community similarity (Jaccard over member sets).

Pure in-memory tests with hand-checked Jaccard values; no store required.
"""

from __future__ import annotations

import pytest

from kg_retrievers.community_similarity import (
    SimilarityResult,
    community_similarity,
    most_similar,
)


def test_identical_sets_score_one() -> None:
    assert community_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_disjoint_sets_score_zero() -> None:
    assert community_similarity({"a", "b"}, {"c", "d"}) == 0.0


def test_partial_overlap_exact_value() -> None:
    # intersection {a, b} = 2, union {a, b, c, d} = 4 -> 0.5
    assert community_similarity({"a", "b", "c"}, {"a", "b", "d"}) == pytest.approx(0.5)


def test_partial_overlap_uneven_sizes() -> None:
    # intersection {a} = 1, union {a, b, c} = 3 -> 1/3
    assert community_similarity({"a", "b"}, {"a", "c"}) == pytest.approx(1 / 3)


def test_both_empty_score_zero() -> None:
    assert community_similarity(set(), set()) == 0.0


def test_one_empty_score_zero() -> None:
    # empty intersection, union = 2 -> 0.0
    assert community_similarity({"a", "b"}, set()) == 0.0


def test_most_similar_picks_best_candidate() -> None:
    communities = {
        "t": {"a", "b", "c"},
        "x": {"a", "b", "c", "d"},  # jaccard 3/4 = 0.75
        "y": {"a", "e"},  # jaccard 1/4 = 0.25
        "z": {"f", "g"},  # jaccard 0.0
    }
    result = most_similar(communities, "t")
    assert result.community_id == "x"
    assert result.score == pytest.approx(0.75)


def test_most_similar_excludes_self() -> None:
    # target is identical to itself (1.0) but must be excluded; best other is y.
    communities = {
        "t": {"a", "b"},
        "y": {"a", "b", "c"},  # jaccard 2/3
    }
    result = most_similar(communities, "t")
    assert result.community_id == "y"
    assert result.score == pytest.approx(2 / 3)


def test_most_similar_single_community_returns_empty() -> None:
    result = most_similar({"only": {"a", "b"}}, "only")
    assert result.community_id is None
    assert result.score == 0.0


def test_most_similar_ties_break_by_ascending_id() -> None:
    communities = {
        "t": {"a", "b"},
        "m": {"a"},  # jaccard 1/2
        "z": {"b"},  # jaccard 1/2 (tie) -> "m" wins on ascending id
    }
    result = most_similar(communities, "t")
    assert result.community_id == "m"
    assert result.score == pytest.approx(0.5)


def test_most_similar_missing_target_raises() -> None:
    with pytest.raises(KeyError):
        most_similar({"a": {"x"}}, "nope")


def test_as_dict_reports_all_fields() -> None:
    result = SimilarityResult(community_id="x", score=0.75)
    assert result.as_dict() == {"community_id": "x", "score": 0.75}


def test_as_dict_empty_result() -> None:
    assert SimilarityResult(community_id=None, score=0.0).as_dict() == {
        "community_id": None,
        "score": 0.0,
    }
