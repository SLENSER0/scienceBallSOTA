"""Tests for §11.6 community-boost re-ranking (hand-checkable, pure python)."""

from __future__ import annotations

from pytest import approx

from kg_retrievers.community_boost import (
    DEFAULT_BOOST,
    BoostedChunk,
    apply_community_boost,
)


def _chunk(chunk_id: str, score: float, community_id: str | None) -> dict:
    return {"chunk_id": chunk_id, "score": score, "community_id": community_id}


def test_matching_community_gains_exactly_default_boost() -> None:
    # base 0.5, community c1 in boost set → 0.5 + 0.2 = 0.7 ровно.
    out = apply_community_boost([_chunk("a", 0.5, "c1")], {"c1"})
    assert len(out) == 1
    assert out[0].base_score == 0.5
    assert out[0].boosted_score == approx(0.7)
    assert out[0].boosted_score - out[0].base_score == approx(DEFAULT_BOOST)


def test_non_matching_community_keeps_base_score() -> None:
    out = apply_community_boost([_chunk("a", 0.5, "c9")], {"c1"})
    assert out[0].boosted_score == 0.5
    assert out[0].boosted_score == out[0].base_score


def test_none_community_is_never_boosted() -> None:
    # Даже если None as membership, буста нет.
    out = apply_community_boost([_chunk("a", 0.5, None)], {"c1"})
    assert out[0].community_id is None
    assert out[0].boosted_score == 0.5


def test_boosted_lower_base_overtakes_unboosted_higher_base() -> None:
    # a: base 0.5, not boosted → 0.5. b: base 0.4, boosted → 0.6. b должен быть выше.
    chunks = [_chunk("a", 0.5, "cx"), _chunk("b", 0.4, "c1")]
    out = apply_community_boost(chunks, {"c1"})
    assert [c.chunk_id for c in out] == ["b", "a"]
    assert out[0].boosted_score == approx(0.6)
    assert out[1].boosted_score == 0.5


def test_equal_boosted_scores_break_ties_by_chunk_id_ascending() -> None:
    # Оба дают boosted 0.5 → сортировка по chunk_id возр.: b3 < d1 < z0? нет: b3,d1,z0.
    chunks = [
        _chunk("z0", 0.5, None),
        _chunk("b3", 0.3, "c1"),  # 0.3 + 0.2 = 0.5
        _chunk("d1", 0.5, "cx"),
    ]
    out = apply_community_boost(chunks, {"c1"})
    assert all(c.boosted_score == 0.5 for c in out)
    assert [c.chunk_id for c in out] == ["b3", "d1", "z0"]


def test_empty_chunks_returns_empty_list() -> None:
    assert apply_community_boost([], {"c1"}) == []


def test_as_dict_reflects_boost() -> None:
    out = apply_community_boost([_chunk("a", 0.5, "c1")], {"c1"})
    d = out[0].as_dict()
    assert d == {
        "chunk_id": "a",
        "base_score": 0.5,
        "community_id": "c1",
        "boosted_score": 0.7,
    }


def test_custom_boost_value_applied() -> None:
    out = apply_community_boost([_chunk("a", 1.0, "c1")], {"c1"}, boost=0.5)
    assert out[0].boosted_score == 1.5


def test_frozen_dataclass_is_immutable() -> None:
    bc = BoostedChunk("a", 0.5, "c1", 0.7)
    try:
        bc.boosted_score = 0.9  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("BoostedChunk must be frozen")


def test_full_ranking_is_sorted_descending() -> None:
    chunks = [
        _chunk("a", 0.1, "c1"),  # 0.3
        _chunk("b", 0.9, None),  # 0.9
        _chunk("c", 0.5, "c1"),  # 0.7
        _chunk("d", 0.6, "cx"),  # 0.6
    ]
    out = apply_community_boost(chunks, {"c1"})
    scores = [c.boosted_score for c in out]
    assert scores == sorted(scores, reverse=True)
    assert [c.chunk_id for c in out] == ["b", "c", "d", "a"]
