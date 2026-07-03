"""Tests for the GraphRAG community-level selector (§11.7)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.graphrag_level_selector import (
    BROAD_MARKERS,
    NARROW_MARKERS,
    LevelChoice,
    select_level,
)


def test_broad_overview_query_picks_max_level() -> None:
    choice = select_level("give an overview of the whole field")
    assert choice.level == 2
    assert choice.breadth_score > 0.5


def test_broad_query_hits_configured_max_level() -> None:
    choice = select_level("summary of the landscape and trends", max_level=4)
    assert choice.level == 4
    assert choice.breadth_score == 1.0


def test_narrow_entity_query_picks_level_zero() -> None:
    choice = select_level("what is the exact yield strength of sample S1")
    assert choice.level == 0
    # Two narrow markers ('exact', 'for sample'? no) — 'exact' present, no broad.
    assert choice.breadth_score == 0.0


def test_override_forces_level_and_reason() -> None:
    choice = select_level("give an overview of the whole field", override=1)
    assert choice.level == 1
    assert choice.reason == "override"


def test_override_clamps_above_max_level() -> None:
    choice = select_level("anything at all", override=99)
    assert choice.level == 2
    assert choice.reason == "override"


def test_override_clamps_below_zero() -> None:
    choice = select_level("anything at all", override=-5)
    assert choice.level == 0
    assert choice.reason == "override"


def test_empty_query_returns_mid_default_without_crash() -> None:
    choice = select_level("")
    # max_level=2 → mid_level == 1; no markers → breadth 0.5.
    assert choice.level == 1
    assert choice.breadth_score == 0.5


def test_empty_query_mid_level_scales_with_max_level() -> None:
    choice = select_level("", max_level=4)
    assert choice.level == 2
    assert choice.breadth_score == 0.5


def test_russian_broad_marker_pushes_high() -> None:
    choice = select_level("какие направления развиваются в целом")
    assert choice.level == 2
    assert choice.breadth_score == 1.0


def test_russian_narrow_marker_pushes_low() -> None:
    choice = select_level("какое значение предела текучести")
    assert choice.level == 0
    assert choice.breadth_score == 0.0


def test_mixed_markers_balanced_lands_mid() -> None:
    # One broad ('overview') and one narrow ('value of') → tie → mid level, breadth 0.5.
    choice = select_level("overview of the value of sample properties")
    # 'value of' is narrow, 'for sample' not present; 'overview' broad → but also
    # 'sample' alone is not a marker. Broad=1 (overview), narrow=1 (value of).
    assert choice.level == 1
    assert choice.breadth_score == 0.5


def test_breadth_score_always_within_unit_interval() -> None:
    queries = [
        "",
        "overview landscape trends summary в целом",
        "exact value of sample specifically конкретно",
        "a plain neutral sentence with no markers",
        "overview but also the exact value of it",
    ]
    for q in queries:
        for override in (None, 0, 1, 2, 99, -3):
            choice = select_level(q, override=override)
            assert 0.0 <= choice.breadth_score <= 1.0
            assert 0 <= choice.level <= 2


def test_as_dict_round_trips_reason() -> None:
    choice = select_level("give an overview", override=None)
    d = choice.as_dict()
    assert d["reason"] == choice.reason
    assert d["level"] == choice.level
    assert d["breadth_score"] == choice.breadth_score


def test_as_dict_round_trips_override_reason() -> None:
    d = select_level("q", override=1).as_dict()
    assert d["reason"] == "override"


def test_level_choice_is_frozen() -> None:
    choice = select_level("overview")
    with pytest.raises(dataclasses.FrozenInstanceError):
        choice.level = 5  # type: ignore[misc]


def test_case_insensitive_matching() -> None:
    choice = select_level("GIVE AN OVERVIEW OF THE LANDSCAPE")
    assert choice.level == 2
    assert choice.breadth_score == 1.0


def test_marker_tables_are_nonempty_and_disjoint() -> None:
    assert BROAD_MARKERS
    assert NARROW_MARKERS
    assert not (set(BROAD_MARKERS) & set(NARROW_MARKERS))


def test_isinstance_level_choice() -> None:
    assert isinstance(select_level("overview"), LevelChoice)
