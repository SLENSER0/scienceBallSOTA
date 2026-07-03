"""Tests for the §5.2.7 / §17.14 gap dashboard ranked list."""

from __future__ import annotations

import json

from kg_retrievers.gap_ranked_list import (
    GAP_TYPE_STYLE,
    GapRankedList,
    build_gap_ranked_list,
)
from kg_schema.enums import GapType


def test_style_covers_every_gap_type_and_hollow_tracks_missing() -> None:
    # An entry for every GapType member.
    assert set(GAP_TYPE_STYLE) == {g.value for g in GapType}
    # hollow == True iff the value starts with 'missing_'.
    for t, style in GAP_TYPE_STYLE.items():
        assert style["hollow"] is (t.startswith("missing_"))
        assert set(style) == {"iconKey", "colorToken", "hollow", "label_ru"}


def test_ranks_map_to_descending_score() -> None:
    gaps = [
        {"gap_id": "g-low", "type": "orphan_entity", "severity": "low", "score": 0.5},
        {"gap_id": "g-high", "type": "unverified_claim", "severity": "high", "score": 0.9},
        {"gap_id": "g-mid", "type": "missing_unit", "severity": "med", "score": 0.7},
    ]
    result = build_gap_ranked_list(gaps)
    assert isinstance(result, GapRankedList)
    assert result.total == 3

    by_rank = {r["rank"]: r for r in result.rows}
    assert by_rank[1]["gap_id"] == "g-high"  # 0.9
    assert by_rank[2]["gap_id"] == "g-mid"  # 0.7
    assert by_rank[3]["gap_id"] == "g-low"  # 0.5


def test_each_row_style_matches_type_style() -> None:
    gaps = [
        {"gap_id": "a", "type": "missing_baseline", "severity": "low", "score": 0.3},
        {"gap_id": "b", "type": "contradictory_measurements", "severity": "high", "score": 0.8},
    ]
    result = build_gap_ranked_list(gaps)
    for row in result.rows:
        assert row["style"] == GAP_TYPE_STYLE[row["type"]]


def test_type_filter_keeps_only_matching() -> None:
    gaps = [
        {"gap_id": "o1", "type": "orphan_entity", "severity": "low", "score": 0.6},
        {"gap_id": "m1", "type": "missing_unit", "severity": "low", "score": 0.9},
        {"gap_id": "o2", "type": "orphan_entity", "severity": "low", "score": 0.4},
    ]
    result = build_gap_ranked_list(gaps, type_filter={"orphan_entity"})
    assert result.total == 2
    assert {r["gap_id"] for r in result.rows} == {"o1", "o2"}
    assert all(r["type"] == "orphan_entity" for r in result.rows)


def test_ties_break_by_gap_id_ascending() -> None:
    gaps = [
        {"gap_id": "zeta", "type": "orphan_entity", "severity": "low", "score": 0.5},
        {"gap_id": "alpha", "type": "orphan_entity", "severity": "low", "score": 0.5},
        {"gap_id": "mid", "type": "orphan_entity", "severity": "low", "score": 0.5},
    ]
    result = build_gap_ranked_list(gaps)
    assert [r["gap_id"] for r in result.rows] == ["alpha", "mid", "zeta"]
    assert [r["rank"] for r in result.rows] == [1, 2, 3]


def test_type_legend_lists_only_present_distinct_types() -> None:
    gaps = [
        {"gap_id": "a", "type": "orphan_entity", "severity": "low", "score": 0.9},
        {"gap_id": "b", "type": "orphan_entity", "severity": "low", "score": 0.8},
        {"gap_id": "c", "type": "missing_unit", "severity": "low", "score": 0.7},
    ]
    result = build_gap_ranked_list(gaps)
    legend_types = [t["type"] for t in result.type_legend]
    # Only distinct types present, first-appearance (rank) order.
    assert legend_types == ["orphan_entity", "missing_unit"]
    for entry in result.type_legend:
        assert entry["style"] == GAP_TYPE_STYLE[entry["type"]]


def test_as_dict_is_json_serialisable() -> None:
    gaps = [
        {"gap_id": "a", "type": "missing_unit", "severity": "low", "score": 0.9},
        {"gap_id": "b", "type": "orphan_entity", "severity": "high", "score": 0.5},
    ]
    result = build_gap_ranked_list(gaps)
    payload = result.as_dict()
    assert set(payload) == {"rows", "typeLegend", "total"}
    assert payload["total"] == 2

    text = json.dumps(payload)
    reloaded = json.loads(text)
    assert reloaded["total"] == 2
    assert reloaded["rows"][0]["rank"] == 1


def test_empty_input_yields_empty_list() -> None:
    result = build_gap_ranked_list([])
    assert result.total == 0
    assert result.rows == ()
    assert result.type_legend == ()
    assert json.dumps(result.as_dict())
