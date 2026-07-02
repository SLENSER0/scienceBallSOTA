"""Splink-lite entity resolution tests (§8.5–8.9)."""

from __future__ import annotations

from kg_extractors.er_advanced import (
    Cluster,
    blocking,
    resolve_records,
    score_pair,
)
from kg_schema.enums import MatchDecision

REVIEW_FLOOR = 0.75

# The four surface forms from the brief: two alloy variants + a cross-lingual
# reverse-osmosis pair. Aliases carry the overlap that makes them resolvable.
RECORDS = [
    {"name": "Al-Cu 2024", "aliases": ["AA2024", "2024 alloy"]},
    {"name": "AA2024 alloy", "aliases": ["Al-Cu 2024", "duralumin"]},
    {"name": "reverse osmosis", "aliases": ["RO", "обратный осмос"]},
    {"name": "обратный осмос", "aliases": ["reverse osmosis", "RO"]},
]


def _cluster_of(clusters: list[Cluster], name: str) -> Cluster:
    for c in clusters:
        if name in c.names:
            return c
    raise AssertionError(f"{name!r} not in any cluster")


def test_blocking_pairs_only_share_a_block_key() -> None:
    pairs = blocking(RECORDS)
    # alloy variants (0,1) and RO variants (2,3) block together...
    assert (0, 1) in pairs
    assert (2, 3) in pairs
    # ...but an alloy never blocks against reverse osmosis (no shared token).
    assert (0, 2) not in pairs
    assert (1, 3) not in pairs
    # deterministic & no self/duplicate pairs
    assert pairs == sorted(set(pairs))


def test_score_pair_symmetric_and_bounded() -> None:
    s01 = score_pair(RECORDS[0], RECORDS[1])
    assert s01 == score_pair(RECORDS[1], RECORDS[0])  # symmetric
    assert 0.0 <= s01 <= 1.0
    # cross-lingual alias overlap => perfect match despite different names
    assert score_pair(RECORDS[2], RECORDS[3]) == 1.0
    # unrelated concepts score well below the review band
    assert score_pair(RECORDS[0], RECORDS[2]) < REVIEW_FLOOR


def test_resolve_clusters_variants_and_keeps_unrelated_separate() -> None:
    clusters = resolve_records(RECORDS)

    alloy = _cluster_of(clusters, "Al-Cu 2024")
    osmosis = _cluster_of(clusters, "reverse osmosis")

    # alloy variants merged together
    assert set(alloy.members) == {0, 1}
    assert alloy.decision is MatchDecision.AUTO_MERGE
    # RO variants merged together (cross-lingual)
    assert set(osmosis.members) == {2, 3}
    assert osmosis.decision is MatchDecision.AUTO_MERGE
    # the two clusters are distinct — alloys are NOT lumped with osmosis
    assert alloy is not osmosis
    assert 2 not in alloy.members and 3 not in alloy.members
    # every record accounted for exactly once
    assert sorted(m for c in clusters for m in c.members) == [0, 1, 2, 3]


def test_deterministic() -> None:
    a = resolve_records(RECORDS)
    b = resolve_records(RECORDS)
    assert [(c.members, c.decision, c.score) for c in a] == [
        (c.members, c.decision, c.score) for c in b
    ]


def test_review_band_flags_borderline_pair() -> None:
    # near-duplicate but below auto (~0.81): must be flagged, not auto-merged.
    recs = [
        {"name": "nanofiltration", "aliases": []},
        {"name": "nanofiltration membrane", "aliases": []},
    ]
    clusters = resolve_records(recs)
    assert len(clusters) == 2  # not merged
    assert all(c.decision is MatchDecision.REVIEW_NEEDED for c in clusters)
    assert all(len(c.members) == 1 for c in clusters)


def test_isolated_record_is_separate() -> None:
    recs = [
        {"name": "reverse osmosis", "aliases": ["RO"]},
        {"name": "membrane distillation", "aliases": ["MD"]},
    ]
    clusters = resolve_records(recs)
    assert len(clusters) == 2
    assert all(c.decision is MatchDecision.SEPARATE for c in clusters)


def test_custom_thresholds_change_decision() -> None:
    recs = [
        {"name": "nanofiltration", "aliases": []},
        {"name": "nanofiltration membrane", "aliases": []},
    ]
    # lowering the auto bar below the pair score forces an auto-merge.
    merged = resolve_records(recs, auto=0.8, review=0.5)
    assert len(merged) == 1
    assert merged[0].decision is MatchDecision.AUTO_MERGE
    assert set(merged[0].members) == {0, 1}
