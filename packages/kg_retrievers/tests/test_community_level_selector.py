"""Tests for the GraphRAG community-level selector (§11.7)."""

from __future__ import annotations

from kg_retrievers.community_level_selector import (
    LevelChoice,
    breadth_score,
    select_level,
)


def test_broad_ru_query_is_global_at_max_level() -> None:
    """A broad RU query ('какие направления') answers from the top of the hierarchy."""
    choice = select_level("какие направления были в теме", max_level=3)
    assert choice.breadth == "global"
    assert choice.level == 3  # == max_level


def test_numeric_unit_query_is_narrow_at_level_zero() -> None:
    """A measurement query ('320 MPa hardness') answers from the entity-level bottom."""
    choice = select_level("320 MPa hardness", max_level=3)
    assert choice.breadth == "narrow"
    assert choice.level == 0


def test_override_short_circuits_with_reason() -> None:
    """An explicit override wins immediately with ``reason='override'``."""
    choice = select_level("any query text", max_level=3, override=1)
    assert choice.level == 1
    assert choice.reason == "override"


def test_override_is_clamped_to_max_level() -> None:
    """An out-of-range override is clamped to ``max_level``."""
    choice = select_level("any query text", max_level=3, override=9)
    assert choice.level == 3
    assert choice.reason == "override"


def test_broad_scores_above_narrow() -> None:
    """A broad query scores strictly higher breadth than a narrow one."""
    broad = breadth_score("overview of the research landscape and directions")
    narrow = breadth_score("exact value of 320 MPa for sample S1")
    assert broad > narrow


def test_breadth_score_is_bounded() -> None:
    """``breadth_score`` never leaves ``[0, 1]`` for any query."""
    queries = [
        "",
        "overview обзор landscape trends directions в целом",
        "320 MPa 45 HRC 900 °C steel alloy titanium образец",
        "a neutral sentence with no strong signals",
    ]
    for q in queries:
        score = breadth_score(q)
        assert 0.0 <= score <= 1.0


def test_as_dict_keys() -> None:
    """``as_dict`` exposes exactly the four documented keys."""
    choice = LevelChoice(level=2, breadth="regional", score=0.5, reason="mid")
    assert set(choice.as_dict().keys()) == {"level", "breadth", "score", "reason"}
