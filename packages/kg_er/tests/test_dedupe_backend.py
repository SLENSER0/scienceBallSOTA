"""Tests for the transparent blocking+scoring dedupe backend (§8.11).

Hand-checked against RU metallurgy equipment names. Two furnace families are used
so blocking (prefix "печ" vs "вак") both prunes comparisons and keeps the families
apart, while abbreviation/variant pairs inside a family still merge.
"""

from __future__ import annotations

import pytest
from kg_er.dedupe_backend import (
    BlockingStats,
    block_key,
    blocking_stats,
    candidate_pairs,
    dedupe_clusters,
    similarity,
)

# e1/e2 = flash-smelting furnace + its abbreviation (ПВП); e3/e4 = vacuum-arc
# furnace + a hyphenated spelling; e5/e6 = unrelated singletons.
ROWS = [
    {"unique_id": "e1", "name": "печь взвешенной плавки"},
    {"unique_id": "e2", "name": "печь ПВП"},
    {"unique_id": "e3", "name": "вакуумная дуговая печь"},
    {"unique_id": "e4", "name": "вакуумно-дуговая печь"},
    {"unique_id": "e5", "name": "прокатный стан"},
    {"unique_id": "e6", "name": "шаровая мельница"},
]


def _merged(clusters) -> set[frozenset[str]]:
    return {frozenset(c.members) for c in clusters if len(c.members) > 1}


def test_block_key_values() -> None:
    # "й" NFKD-folds to "и"; hyphen is kept so "вакуумно-дуговая" is one token.
    assert block_key("печь ПВП") == frozenset({"пвп печь", "печ"})
    assert block_key("вакуумно-дуговая печь") == frozenset({"вакуумно-дуговая печь", "вак"})
    assert block_key("   ") == frozenset()  # empty name -> no keys


def test_similarity_first_token_boost() -> None:
    # token_set_ratio("печь взвешеннои плавки","печь пвп") == 66.67 -> 0.6667,
    # shared leading token "печь" adds the 0.15 boost.
    raw = similarity("печь взвешенной плавки", "печь пвп", boost=0.0)
    boosted = similarity("печь взвешенной плавки", "печь ПВП")
    assert raw == pytest.approx(0.6667, abs=1e-3)
    assert boosted == pytest.approx(0.8167, abs=1e-3)
    assert boosted > raw
    # distinct machines: no shared token, well below the default threshold.
    assert similarity("прокатный стан", "шаровая мельница") == pytest.approx(0.2667, abs=1e-3)


def test_obvious_duplicates_cluster() -> None:
    clusters = dedupe_clusters("Equipment", ROWS, threshold=0.55)
    assert _merged(clusters) == {frozenset({"e1", "e2"}), frozenset({"e3", "e4"})}
    hi = next(c for c in clusters if set(c.members) == {"e3", "e4"})
    assert hi.max_probability == pytest.approx(0.8837, abs=1e-3)


def test_distinct_entities_stay_separate() -> None:
    clusters = dedupe_clusters("Equipment", ROWS, threshold=0.55)
    singletons = {c.members[0] for c in clusters if len(c.members) == 1}
    assert singletons == {"e5", "e6"}
    # the two furnace families never land in the same cluster
    assert not any({"e1", "e3"} <= set(c.members) for c in clusters)


def test_blocking_reduces_pair_count() -> None:
    pairs = candidate_pairs(ROWS)
    assert pairs == [("e1", "e2"), ("e3", "e4")]  # only within-block comparisons
    stats = blocking_stats(ROWS)
    assert isinstance(stats, BlockingStats)
    assert stats.n_all_pairs == 15  # C(6, 2)
    assert stats.n_candidate_pairs == 2
    assert stats.reduction_ratio == pytest.approx(1 - 2 / 15)
    assert stats.as_dict()["n_candidate_pairs"] == 2


def test_singleton_and_empty_input() -> None:
    assert dedupe_clusters("Equipment", []) == []
    one = dedupe_clusters("Equipment", [ROWS[0]])
    assert len(one) == 1
    assert one[0].members == ("e1",)
    assert one[0].max_probability == 0.0
    assert one[0].pair_probabilities == {}


def test_threshold_monotonicity() -> None:
    # scores: {e1,e2}=0.8167, {e3,e4}=0.8837 -> merges fall as the bar rises.
    counts = [
        len(_merged(dedupe_clusters("Equipment", ROWS, threshold=t))) for t in (0.55, 0.85, 0.95)
    ]
    assert counts == [2, 1, 0]
    assert counts == sorted(counts, reverse=True)  # non-increasing


def test_every_id_in_exactly_one_cluster() -> None:
    clusters = dedupe_clusters("Equipment", ROWS, threshold=0.55)
    members = [m for c in clusters for m in c.members]
    assert len(members) == len(set(members)) == len(ROWS)  # a true partition
    assert set(members) == {r["unique_id"] for r in ROWS}
