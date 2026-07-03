"""Tests for GraphRAG community listing and detail views (§11.9)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.graphrag_communities_listing import (
    CommunityListing,
    CommunityListItem,
    community_detail,
    list_communities,
)


def _reports() -> list[dict]:
    """Five community reports across levels 0 and 1 with distinct ranks."""
    return [
        {
            "community_id": "c0a",
            "title": "Fine cluster A",
            "level": 0,
            "rank": 0.10,
            "summary": "entity-level A",
            "findings": ["f1"],
            "cited_doc_ids": ["d1"],
            "sub_communities": [],
        },
        {
            "community_id": "c0b",
            "title": "Fine cluster B",
            "level": 0,
            "rank": 0.90,
            "summary": "entity-level B",
            "findings": ["f2", "f3"],
            "cited_doc_ids": ["d2", "d3"],
            "sub_communities": [],
        },
        {
            "community_id": "c1a",
            "title": "Broad cluster A",
            "level": 1,
            "rank": 0.50,
            "summary": "global A",
            "findings": [],
            "cited_doc_ids": ["d4"],
            "sub_communities": ["c0a"],
        },
        {
            "community_id": "c1b",
            "title": "Broad cluster B",
            "level": 1,
            "rank": 0.80,
            "summary": "global B",
            "findings": ["f4"],
            "cited_doc_ids": [],
            "sub_communities": ["c0b"],
        },
        {
            "community_id": "c1c",
            "title": "Broad cluster C",
            "level": 1,
            "rank": 0.30,
            "summary": "global C",
            "findings": [],
            "cited_doc_ids": ["d5"],
            "sub_communities": [],
        },
    ]


def test_level_filter_excludes_other_levels_and_sets_total() -> None:
    listing = list_communities(_reports(), level=1)
    assert all(item.level == 1 for item in listing.items)
    assert listing.total == 3  # three level-1 reports
    assert listing.level_filter == 1


def test_no_filter_includes_all_levels() -> None:
    listing = list_communities(_reports())
    assert listing.total == 5
    assert listing.level_filter is None


def test_sorted_by_descending_rank() -> None:
    listing = list_communities(_reports())
    ranks = [item.rank for item in listing.items]
    assert ranks == [0.90, 0.80, 0.50, 0.30, 0.10]
    assert listing.items[0].community_id == "c0b"  # highest rank first


def test_limit_and_offset_returns_second_and_third_items() -> None:
    listing = list_communities(_reports(), limit=2, offset=1)
    # Full sorted order: c0b(.90), c1b(.80), c1a(.50), c1c(.30), c0a(.10).
    ids = [item.community_id for item in listing.items]
    assert ids == ["c1b", "c1a"]  # 2nd and 3rd
    assert listing.total == 5  # total independent of the window


def test_total_independent_of_limit() -> None:
    small = list_communities(_reports(), limit=1)
    big = list_communities(_reports(), limit=100)
    assert small.total == big.total == 5
    assert len(small.items) == 1
    assert len(big.items) == 5


def test_community_id_ascending_breaks_rank_ties() -> None:
    tied = [
        {"community_id": "z", "title": "Z", "level": 0, "rank": 0.5},
        {"community_id": "a", "title": "A", "level": 0, "rank": 0.5},
        {"community_id": "m", "title": "M", "level": 0, "rank": 0.5},
    ]
    listing = list_communities(tied)
    assert [item.community_id for item in listing.items] == ["a", "m", "z"]


def test_community_detail_known_id_returns_summary() -> None:
    report = community_detail(_reports(), "c0b")
    assert report is not None
    assert report["summary"] == "entity-level B"
    assert report["findings"] == ["f2", "f3"]
    assert report["cited_doc_ids"] == ["d2", "d3"]
    assert report["sub_communities"] == []


def test_community_detail_unknown_id_returns_none() -> None:
    assert community_detail(_reports(), "does-not-exist") is None


def test_community_detail_includes_sub_communities() -> None:
    report = community_detail(_reports(), "c1a")
    assert report is not None
    assert report["sub_communities"] == ["c0a"]


def test_empty_reports_yields_zero_total_and_no_items() -> None:
    listing = list_communities([])
    assert listing.total == 0
    assert listing.items == []


def test_empty_reports_detail_returns_none() -> None:
    assert community_detail([], "anything") is None


def test_as_dict_echoes_level_filter() -> None:
    assert list_communities(_reports(), level=0).as_dict()["level_filter"] == 0
    assert list_communities(_reports()).as_dict()["level_filter"] is None


def test_listing_as_dict_round_trips_items_and_total() -> None:
    listing = list_communities(_reports(), level=1, limit=2)
    d = listing.as_dict()
    assert d["total"] == 3
    assert len(d["items"]) == 2
    assert d["items"][0]["community_id"] == "c1b"  # highest-rank level-1
    assert d["items"][0]["rank"] == 0.80


def test_list_item_as_dict_has_all_fields() -> None:
    item = list_communities(_reports()).items[0]
    d = item.as_dict()
    assert set(d) == {"community_id", "title", "level", "rank"}
    assert d["community_id"] == "c0b"


def test_offset_past_end_returns_empty_page_but_full_total() -> None:
    listing = list_communities(_reports(), offset=100)
    assert listing.items == []
    assert listing.total == 5


def test_list_item_is_frozen() -> None:
    item = CommunityListItem(community_id="x", title="X", level=0, rank=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.rank = 2.0  # type: ignore[misc]


def test_listing_is_frozen() -> None:
    listing = list_communities(_reports())
    with pytest.raises(dataclasses.FrozenInstanceError):
        listing.total = 0  # type: ignore[misc]


def test_isinstance_types() -> None:
    listing = list_communities(_reports())
    assert isinstance(listing, CommunityListing)
    assert isinstance(listing.items[0], CommunityListItem)
