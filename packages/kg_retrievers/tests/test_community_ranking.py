"""Tests for §11.19 community-report ranking.

Pure in-memory transform: each test hands :func:`rank_communities` a small list of
report dicts with hand-checked size / findings / rank values and asserts concrete
scores and orderings.
"""

from __future__ import annotations

import json

from kg_retrievers.community_ranking import (
    CommunityRank,
    rank_communities,
    top_communities,
)


def test_three_reports_sorted_by_score_desc() -> None:
    reports = [
        {"community_id": 1, "level": 0, "size": 10, "n_findings": 5, "rank": 0.9},
        {"community_id": 2, "level": 0, "size": 4, "n_findings": 2, "rank": 0.3},
        {"community_id": 3, "level": 0, "size": 7, "n_findings": 8, "rank": 0.5},
    ]
    ranked = rank_communities(reports)
    assert len(ranked) == 3
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    # Hand-checked (max_size=10, max_findings=8, max_rank=0.9; weights 0.4/0.3/0.3):
    #   id1 = 0.4*1.0    + 0.3*0.625 + 0.3*1.0     = 0.8875
    #   id3 = 0.4*0.7    + 0.3*1.0   + 0.3*0.55556 = 0.746667
    #   id2 = 0.4*0.4    + 0.3*0.25  + 0.3*0.33333 = 0.335
    assert [r.community_id for r in ranked] == [1, 3, 2]
    assert ranked[0].score == 0.8875
    assert ranked[2].score == 0.335


def test_dominant_report_ranks_first() -> None:
    reports = [
        {"community_id": 1, "level": 0, "size": 20, "n_findings": 10, "rank": 1.0},
        {"community_id": 2, "level": 0, "size": 5, "n_findings": 3, "rank": 0.4},
        {"community_id": 3, "level": 0, "size": 8, "n_findings": 6, "rank": 0.7},
    ]
    ranked = rank_communities(reports)
    # id1 is the maximum in size, findings AND rank -> every normalised metric is 1.0.
    assert ranked[0].community_id == 1
    assert ranked[0].score == 1.0


def test_score_tie_broken_by_ascending_community_id() -> None:
    reports = [
        {"community_id": 5, "level": 0, "size": 10, "n_findings": 4, "rank": 0.5},
        {"community_id": 2, "level": 0, "size": 10, "n_findings": 4, "rank": 0.5},
        {"community_id": 9, "level": 0, "size": 10, "n_findings": 4, "rank": 0.5},
    ]
    ranked = rank_communities(reports)
    # Identical metrics -> identical scores; ties resolve by ascending community_id.
    assert len({r.score for r in ranked}) == 1
    assert [r.community_id for r in ranked] == [2, 5, 9]


def test_custom_weights_change_ordering() -> None:
    reports = [
        {"community_id": 1, "level": 0, "size": 2, "n_findings": 10, "rank": 1.0},
        {"community_id": 2, "level": 0, "size": 10, "n_findings": 1, "rank": 0.1},
    ]
    # Default weights favour the findings/rank-heavy report (id1).
    assert [r.community_id for r in rank_communities(reports)] == [1, 2]
    # Size-only weights favour the large-but-thin report (id2); ordering flips.
    size_only = rank_communities(reports, weights={"size": 1.0, "findings": 0.0, "rank": 0.0})
    assert [r.community_id for r in size_only] == [2, 1]


def test_score_normalised_within_unit_interval() -> None:
    reports = [
        {"community_id": 1, "level": 0, "size": 10, "n_findings": 5, "rank": 0.9},
        {"community_id": 2, "level": 0, "size": 4, "n_findings": 2, "rank": 0.3},
        {"community_id": 3, "level": 0, "size": 7, "n_findings": 8, "rank": 0.5},
    ]
    for record in rank_communities(reports):
        assert 0.0 <= record.score <= 1.0


def test_top_communities_returns_two_highest_scoring_ids() -> None:
    reports = [
        {"community_id": 9, "level": 0, "size": 20, "n_findings": 10, "rank": 1.0},
        {"community_id": 1, "level": 0, "size": 5, "n_findings": 3, "rank": 0.4},
        {"community_id": 5, "level": 0, "size": 8, "n_findings": 6, "rank": 0.7},
    ]
    # Scores: id9=1.0 > id5=0.55 > id1=0.31 -> the two highest-scoring ids are 9 then 5.
    assert top_communities(reports, 2) == [9, 5]
    assert top_communities(reports, 0) == []


def test_empty_input_and_as_dict_json_serializable() -> None:
    assert rank_communities([]) == []
    assert top_communities([], 3) == []

    record = CommunityRank(
        community_id=7, level=1, size=12, n_findings=4, rank_field=0.6, score=0.5
    )
    payload = record.as_dict()
    assert payload == {
        "community_id": 7,
        "level": 1,
        "size": 12,
        "n_findings": 4,
        "rank_field": 0.6,
        "score": 0.5,
    }
    assert json.loads(json.dumps(payload)) == payload
