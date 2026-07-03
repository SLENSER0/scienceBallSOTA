"""Hand-checkable tests for the LELA zero-shot entity-linking rerank (§8 ER).

Paper: LELA (arXiv:2601.05192), reference implementation (code to-be-released).
"""

from __future__ import annotations

from kg_retrievers import lela_entity_linking as lela
from kg_retrievers.lela_entity_linking import (
    ALIAS_BOOST,
    EXACT_NAME_BOOST,
    LinkResult,
    ScoredCandidate,
    link_entities,
)


def _candidates() -> list[dict[str, object]]:
    """Three distinct KB entities with RU/EN names + aliases (§3.12)."""
    return [
        {"id": "e1", "name": "Reverse Osmosis", "aliases": ["RO", "обратный осмос"]},
        {"id": "e2", "name": "Forward Osmosis", "aliases": ["FO"]},
        {"id": "e3", "name": "Nanofiltration", "aliases": ["NF"]},
    ]


def test_docstring_cites_paper() -> None:
    """Hard rule: module docstring must cite the source paper (arXiv id)."""
    assert "2601.05192" in lela.__doc__
    assert "to-be-released" in lela.__doc__


def test_exact_name_ranks_first() -> None:
    """Exact canonical-name match scores base(1.0)+EXACT_NAME_BOOST and ranks #1."""
    result = link_entities("Reverse Osmosis", _candidates())
    assert result.ranked[0].id == "e1"
    # base exact (1.0) + exact-name boost (1.0) == 2.0.
    assert result.ranked[0].score == round(1.0 + EXACT_NAME_BOOST, 4)
    assert result.best == "e1"
    assert result.is_nil is False


def test_alias_match_wins_over_fuzzy() -> None:
    """Exact alias match (base 1.0 + ALIAS_BOOST) links, beating fuzzy names."""
    cands = [
        {"id": "e1", "name": "Reverse Osmosis", "aliases": ["RO"]},
        {"id": "e9", "name": "Robotics"},  # 'ro' is only a prefix here
    ]
    result = link_entities("RO", cands)
    assert result.best == "e1"
    assert result.ranked[0].id == "e1"
    assert result.ranked[0].score == round(1.0 + ALIAS_BOOST, 4)
    assert result.is_nil is False


def test_ambiguous_close_scores_abstains_nil() -> None:
    """Two entities sharing the exact same alias → equal scores → abstain (NIL)."""
    cands = [
        {"id": "e1", "name": "Reverse Osmosis", "aliases": ["osmosis"]},
        {"id": "e2", "name": "Forward Osmosis", "aliases": ["osmosis"]},
    ]
    result = link_entities("osmosis", cands)
    # both score 1.0 + ALIAS_BOOST → margin 0 < NIL_MARGIN.
    assert result.is_nil is True
    assert result.best is None
    assert len(result.ranked) == 2
    assert result.ranked[0].score == result.ranked[1].score


def test_no_candidates_is_nil() -> None:
    """No candidates → nothing to link → NIL abstention, empty ranking."""
    result = link_entities("Reverse Osmosis", [])
    assert result.is_nil is True
    assert result.best is None
    assert result.ranked == ()


def test_no_surface_match_is_nil() -> None:
    """Candidates exist but none match the mention → base 0 → NIL."""
    cands = [{"id": "e3", "name": "Nanofiltration", "aliases": ["NF"]}]
    result = link_entities("photosynthesis quantum yield", cands)
    assert result.is_nil is True
    assert result.best is None
    assert result.ranked == ()


def test_top_k_caps_ranked_length() -> None:
    """top_k bounds the returned ranking even with many matching candidates."""
    cands = [{"id": f"e{i}", "name": f"Osmosis Variant {i}"} for i in range(6)]
    result = link_entities("osmosis", cands, top_k=2)
    assert len(result.ranked) == 2


def test_best_is_highest_scoring() -> None:
    """When committing, best == the top-ranked (max-score) candidate id."""
    result = link_entities("Reverse Osmosis", _candidates())
    top = max(result.ranked, key=lambda c: c.score)
    assert result.best == top.id
    assert result.ranked[0].id == top.id
    assert all(result.ranked[0].score >= c.score for c in result.ranked)


def test_ranked_sorted_descending() -> None:
    """Ranking is strictly non-increasing by score (ties broken by id)."""
    result = link_entities("Reverse Osmosis", _candidates())
    scores = [c.score for c in result.ranked]
    assert scores == sorted(scores, reverse=True)


def test_as_dict_shape() -> None:
    """LinkResult.as_dict → {mention, ranked:[{id,score}], best, is_nil}."""
    result = link_entities("Reverse Osmosis", _candidates())
    payload = result.as_dict()
    assert payload["mention"] == "Reverse Osmosis"
    assert payload["best"] == "e1"
    assert payload["is_nil"] is False
    assert payload["ranked"][0] == {"id": "e1", "score": result.ranked[0].score}
    assert all(set(item) == {"id", "score"} for item in payload["ranked"])


def test_scored_candidate_is_frozen() -> None:
    """Frozen dataclass — scores are immutable (house style)."""
    cand = ScoredCandidate(id="e1", score=2.0)
    try:
        cand.score = 3.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ScoredCandidate must be frozen")


def test_link_result_is_frozen() -> None:
    """LinkResult is frozen too (house style)."""
    result = LinkResult(mention="m", ranked=(), best=None, is_nil=True)
    try:
        result.best = "e1"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("LinkResult must be frozen")
