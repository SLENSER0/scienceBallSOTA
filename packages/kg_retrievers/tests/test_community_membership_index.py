"""Tests for the entity→community reverse membership index (§11.6)."""

from __future__ import annotations

from kg_retrievers.community_membership_index import MembershipIndex


def _rows() -> list[dict]:
    # osmosis (осмос) and water (вода) share a community at level 0;
    # membrane (мембрана) is a solo member; at level 1 osmosis moves communities.
    return [
        {"entity_id": "osmosis", "level": 0, "community_id": 7},
        {"entity_id": "water", "level": 0, "community_id": 7},
        {"entity_id": "membrane", "level": 0, "community_id": 9},
        {"entity_id": "osmosis", "level": 1, "community_id": 2},
    ]


def test_from_assignments_counts() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.as_dict() == {"n_assignments": 4}


def test_community_at_returns_mapped_id() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.community_at("osmosis", 0) == 7
    assert idx.community_at("membrane", 0) == 9


def test_community_at_unknown_entity_is_none() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.community_at("не_существует", 0) is None


def test_members_sorted_and_deduped() -> None:
    rows = [*_rows(), {"entity_id": "water", "level": 0, "community_id": 7}]
    idx = MembershipIndex.from_assignments(rows)
    assert idx.members(0, 7) == ("osmosis", "water")


def test_co_members_excludes_self() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.co_members("osmosis", 0) == ("water",)
    assert "osmosis" not in idx.co_members("osmosis", 0)


def test_co_members_of_solo_is_empty() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.co_members("membrane", 0) == ()


def test_entity_in_different_communities_across_levels() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.community_at("osmosis", 0) == 7
    assert idx.community_at("osmosis", 1) == 2
    assert idx.community_at("osmosis", 0) != idx.community_at("osmosis", 1)


def test_members_of_unknown_community_is_empty() -> None:
    idx = MembershipIndex.from_assignments(_rows())
    assert idx.members(0, 999) == ()
