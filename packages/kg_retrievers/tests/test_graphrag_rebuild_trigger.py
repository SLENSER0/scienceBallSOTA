"""Tests for the §11.10 GraphRAG rebuild trigger decision (hand-checked)."""

from __future__ import annotations

from kg_retrievers.graphrag_rebuild_trigger import (
    CORPUS_GROWTH,
    FAILED_BUILD,
    STALE,
    UP_TO_DATE,
    RebuildDecision,
    decide_rebuild,
)


def test_failed_build_fires() -> None:
    d = decide_rebuild(0, 10, 1, 24, "failed")
    assert d.should_rebuild is True
    assert d.reason == FAILED_BUILD == "failed_build"


def test_stale_fires() -> None:
    d = decide_rebuild(5, 10, 30, 24, "built")
    assert d.should_rebuild is True
    assert d.reason == STALE == "stale"


def test_corpus_growth_fires() -> None:
    d = decide_rebuild(20, 10, 1, 24, "built")
    assert d.should_rebuild is True
    assert d.reason == CORPUS_GROWTH == "corpus_growth"


def test_up_to_date() -> None:
    d = decide_rebuild(3, 10, 1, 24, "built")
    assert d.should_rebuild is False
    assert d.reason == UP_TO_DATE == "up_to_date"


def test_failed_build_wins_over_corpus_growth() -> None:
    # Both failed_build and corpus_growth hold; priority gives failed_build.
    d = decide_rebuild(20, 10, 1, 24, "failed")
    assert d.reason == "failed_build"
    assert d.should_rebuild is True


def test_failed_build_wins_over_stale_and_growth() -> None:
    # All three conditions hold at once → failed_build still wins.
    d = decide_rebuild(50, 10, 100, 24, "failed")
    assert d.reason == "failed_build"


def test_stale_wins_over_corpus_growth() -> None:
    # Both stale and corpus_growth hold; stale has higher priority.
    d = decide_rebuild(20, 10, 30, 24, "built")
    assert d.reason == "stale"


def test_stale_boundary_inclusive() -> None:
    # hours_since_last == max_age_hours is stale (>=).
    d = decide_rebuild(0, 10, 24, 24, "built")
    assert d.reason == "stale"


def test_corpus_growth_boundary_inclusive() -> None:
    # n_new_docs == doc_threshold triggers corpus_growth (>=).
    d = decide_rebuild(10, 10, 1, 24, "built")
    assert d.reason == "corpus_growth"


def test_pending_docs_echoes_n_new_docs() -> None:
    for n in (0, 3, 7, 42):
        assert decide_rebuild(n, 10, 1, 24, "built").pending_docs == n
    # Also echoed on a triggered decision.
    assert decide_rebuild(99, 10, 1, 24, "failed").pending_docs == 99


def test_as_dict_round_trips() -> None:
    d = decide_rebuild(7, 10, 1, 24, "built")
    dd = d.as_dict()
    assert dd == {"should_rebuild": False, "reason": "up_to_date", "pending_docs": 7}
    assert RebuildDecision(**dd) == d


def test_frozen_dataclass() -> None:
    d = decide_rebuild(1, 10, 1, 24, "built")
    try:
        d.should_rebuild = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("RebuildDecision must be frozen")
