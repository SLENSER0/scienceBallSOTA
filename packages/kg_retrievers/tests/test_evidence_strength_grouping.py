"""Tests for §24.11 literature-review facet grouping.

Hand-checked assertions over :func:`group_by_facet` and :class:`FacetBucket`.
"""

from __future__ import annotations

import pytest

from kg_retrievers.evidence_strength_grouping import FacetBucket, group_by_facet


def test_method_facet_two_buckets_ro_first() -> None:
    """(1) methods RO,RO,IX → 2 buckets, RO bucket n_sources==2 first."""
    sources = [
        {"source_id": "s1", "method": "RO", "evidence_strength": "high"},
        {"source_id": "s2", "method": "RO", "evidence_strength": "low"},
        {"source_id": "s3", "method": "IX", "evidence_strength": "high"},
    ]
    buckets = group_by_facet(sources, "method")
    assert len(buckets) == 2
    assert buckets[0].key == "RO"
    assert buckets[0].n_sources == 2
    assert buckets[1].key == "IX"
    assert buckets[1].n_sources == 1


def test_duplicate_source_id_counted_once() -> None:
    """(2) same source_id twice in one method → counted once."""
    sources = [
        {"source_id": "s1", "method": "RO", "evidence_strength": "high"},
        {"source_id": "s1", "method": "RO", "evidence_strength": "high"},
    ]
    buckets = group_by_facet(sources, "method")
    assert len(buckets) == 1
    assert buckets[0].n_sources == 1
    assert buckets[0].source_ids == ("s1",)


def test_year_facet_tie_sorted_key_ascending() -> None:
    """(3) years 2020,2019 → keys '2019' before '2020' on n_sources tie."""
    sources = [
        {"source_id": "s1", "year": 2020},
        {"source_id": "s2", "year": 2019},
    ]
    buckets = group_by_facet(sources, "year")
    assert [b.key for b in buckets] == ["2019", "2020"]
    assert all(b.n_sources == 1 for b in buckets)


def test_missing_geography_lands_in_unknown() -> None:
    """(4) a source missing 'geography' → lands in 'unknown' bucket."""
    sources = [
        {"source_id": "s1", "geography": "EU"},
        {"source_id": "s2"},
    ]
    buckets = group_by_facet(sources, "geography")
    keys = {b.key: b for b in buckets}
    assert "unknown" in keys
    assert keys["unknown"].source_ids == ("s2",)


def test_evidence_strength_hist_for_ro_bucket() -> None:
    """(5) evidence_strength_hist for RO with ['high','low'] == both 1."""
    sources = [
        {"source_id": "s1", "method": "RO", "evidence_strength": "high"},
        {"source_id": "s2", "method": "RO", "evidence_strength": "low"},
    ]
    buckets = group_by_facet(sources, "method")
    assert buckets[0].key == "RO"
    assert buckets[0].evidence_strength_hist == {"high": 1, "low": 1}


def test_empty_input_returns_empty_tuple() -> None:
    """(6) empty input → empty tuple."""
    assert group_by_facet([], "method") == ()


def test_as_dict_facet_field() -> None:
    """(7) as_dict()['facet'] == 'method'."""
    sources = [{"source_id": "s1", "method": "RO"}]
    bucket = group_by_facet(sources, "method")[0]
    assert isinstance(bucket, FacetBucket)
    assert bucket.as_dict()["facet"] == "method"


def test_invalid_facet_raises_value_error() -> None:
    """(8) invalid facet name raises ValueError."""
    with pytest.raises(ValueError):
        group_by_facet([{"source_id": "s1"}], "author")
