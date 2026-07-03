"""Tests for literature-review source grouping (§24.11)."""

from __future__ import annotations

from kg_retrievers.review_grouping import (
    UNKNOWN_BUCKET,
    ReviewBuckets,
    bucket_counts,
    group_sources,
)


def test_two_sources_same_method_share_key() -> None:
    """Two sources with the same method land under one ``by_method`` key."""
    buckets = group_sources(
        [
            {"source_id": "s1", "method": "RCT"},
            {"source_id": "s2", "method": "RCT"},
        ]
    )
    assert buckets.by_method == {"RCT": ("s1", "s2")}


def test_missing_method_routes_to_unknown() -> None:
    """A missing or blank method value routes the source into the 'unknown' bucket."""
    buckets = group_sources(
        [
            {"source_id": "s1"},
            {"source_id": "s2", "method": "   "},
            {"source_id": "s3", "method": None},
        ]
    )
    assert buckets.by_method == {UNKNOWN_BUCKET: ("s1", "s2", "s3")}
    assert UNKNOWN_BUCKET == "unknown"


def test_year_coerced_to_string_key() -> None:
    """Integer year 2021 is keyed as '2021'; a string '2021' shares that key."""
    buckets = group_sources(
        [
            {"source_id": "s1", "year": 2021},
            {"source_id": "s2", "year": "2021"},
        ]
    )
    assert buckets.by_year == {"2021": ("s1", "s2")}


def test_duplicate_source_id_collapses() -> None:
    """A duplicate source_id within a bucket collapses to a single entry."""
    buckets = group_sources(
        [
            {"source_id": "s1", "geography": "EU"},
            {"source_id": "s1", "geography": "EU"},
        ]
    )
    assert buckets.by_geography == {"EU": ("s1",)}
    assert buckets.total == 1


def test_total_is_distinct_source_count() -> None:
    """``total`` counts distinct source_id, not records."""
    buckets = group_sources(
        [
            {"source_id": "s1", "method": "RCT"},
            {"source_id": "s2", "method": "cohort"},
            {"source_id": "s1", "method": "meta"},  # same source, second row
        ]
    )
    assert buckets.total == 2
    # s1 appears in two different method buckets (routed by each record's field).
    assert buckets.by_method == {"RCT": ("s1",), "cohort": ("s2",), "meta": ("s1",)}


def test_source_ids_sorted_within_bucket() -> None:
    """Source ids come back ascending-sorted within a bucket regardless of input order."""
    buckets = group_sources(
        [
            {"source_id": "s3", "evidence_strength": "high"},
            {"source_id": "s1", "evidence_strength": "high"},
            {"source_id": "s2", "evidence_strength": "high"},
        ]
    )
    assert buckets.by_evidence_strength == {"high": ("s1", "s2", "s3")}


def test_bucket_counts_maps_key_to_len() -> None:
    """``bucket_counts()['by_method']`` maps each key to its number of source ids."""
    buckets = group_sources(
        [
            {"source_id": "s1", "method": "RCT"},
            {"source_id": "s2", "method": "RCT"},
            {"source_id": "s3", "method": "cohort"},
        ]
    )
    counts = bucket_counts(buckets)
    assert counts["by_method"] == {"RCT": 2, "cohort": 1}
    for axis in ("by_method", "by_year", "by_geography", "by_evidence_strength"):
        assert axis in counts


def test_empty_records_yield_empty_buckets() -> None:
    """Empty input -> total 0 and all four buckets empty."""
    buckets = group_sources([])
    assert buckets.total == 0
    assert buckets.by_method == {}
    assert buckets.by_year == {}
    assert buckets.by_geography == {}
    assert buckets.by_evidence_strength == {}
    assert bucket_counts(buckets) == {
        "by_method": {},
        "by_year": {},
        "by_geography": {},
        "by_evidence_strength": {},
    }


def test_records_without_source_id_are_skipped() -> None:
    """A record lacking a usable source_id contributes nothing."""
    buckets = group_sources(
        [
            {"method": "RCT"},
            {"source_id": "   ", "method": "RCT"},
            {"source_id": "s1", "method": "RCT"},
        ]
    )
    assert buckets.total == 1
    assert buckets.by_method == {"RCT": ("s1",)}


def test_full_multi_axis_grouping() -> None:
    """A hand-checkable record lands in the right key on all four axes at once."""
    buckets = group_sources(
        [
            {
                "source_id": "s1",
                "method": "cohort",
                "year": 2019,
                "geography": "RU",
                "evidence_strength": "medium",
            },
            {
                "source_id": "s2",
                "method": "cohort",
                "year": 2019,
                "geography": "US",
                # evidence_strength missing -> unknown
            },
        ]
    )
    assert buckets.by_method == {"cohort": ("s1", "s2")}
    assert buckets.by_year == {"2019": ("s1", "s2")}
    assert buckets.by_geography == {"RU": ("s1",), "US": ("s2",)}
    assert buckets.by_evidence_strength == {"medium": ("s1",), UNKNOWN_BUCKET: ("s2",)}
    assert buckets.total == 2


def test_as_dict_round_trips_bucket_dicts() -> None:
    """``as_dict()`` reproduces the four bucket dicts (tuples as lists) plus total."""
    buckets = group_sources(
        [
            {"source_id": "s1", "method": "RCT", "year": 2021, "geography": "EU"},
            {"source_id": "s2", "method": "RCT", "year": 2020},
        ]
    )
    payload = buckets.as_dict()
    assert payload["by_method"] == {"RCT": ["s1", "s2"]}
    assert payload["by_year"] == {"2021": ["s1"], "2020": ["s2"]}
    assert payload["by_geography"] == {"EU": ["s1"], UNKNOWN_BUCKET: ["s2"]}
    assert payload["by_evidence_strength"] == {UNKNOWN_BUCKET: ["s1", "s2"]}
    assert payload["total"] == 2
    # Round-trip: rebuilding tuples from as_dict lists reproduces the bucket dicts.
    assert {k: tuple(v) for k, v in payload["by_method"].items()} == buckets.by_method


def test_frozen_dataclass_is_immutable() -> None:
    """``ReviewBuckets`` is frozen — attribute assignment raises."""
    buckets = group_sources([{"source_id": "s1", "method": "RCT"}])
    assert isinstance(buckets, ReviewBuckets)
    try:
        buckets.total = 99  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ReviewBuckets should be immutable")
