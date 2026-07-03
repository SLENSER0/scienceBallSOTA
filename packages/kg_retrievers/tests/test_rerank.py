"""Tests for the MMR + evidence-boost reranker (§12.9), hand-checked values."""

from __future__ import annotations

from kg_retrievers.rerank import RerankedItem, evidence_boost_rerank, mmr_rerank

# Shared MMR fixture: A is top; B is a near-duplicate of A (Jaccard 0.8); C is a
# diverse topic (Jaccard 0.0 vs A) but slightly less relevant than B.
_A = {"id": "A", "score": 1.0, "text": "reverse osmosis desalination membrane"}
_B = {"id": "B", "score": 0.9, "text": "reverse osmosis desalination membrane system"}
_C = {"id": "C", "score": 0.8, "text": "solar thermal power tower"}
_ABC = [_A, _B, _C]


def test_mmr_empty_returns_empty() -> None:
    assert mmr_rerank([]) == []
    assert evidence_boost_rerank([]) == []


def test_mmr_singleton_is_stable() -> None:
    out = mmr_rerank([{"id": "only", "score": 0.42, "text": "lone candidate"}])
    assert len(out) == 1
    item = out[0]
    assert item.id == "only"
    assert item.rank == 0
    assert item.base_score == 0.42
    # max-normalized relevance of a singleton is 1.0 → mmr = lambda_ * 1.0.
    assert item.score == 0.7


def test_mmr_diversifies_second_pick_over_near_duplicate() -> None:
    # Default lambda_=0.7 should prefer the diverse C over the near-duplicate B
    # for the 2nd slot, even though B is more relevant than C.
    out = mmr_rerank(_ABC)
    assert [it.id for it in out] == ["A", "C", "B"]
    # Hand-checked MMR marginals:
    #   A: 0.7*1.0                         = 0.70
    #   C: 0.7*0.8 - 0.3*jaccard(C,A)=0.0  = 0.56
    #   B: 0.7*0.9 - 0.3*jaccard(B,A)=0.8  = 0.39
    assert out[0].score == 0.7
    assert out[1].score == 0.56
    assert out[2].score == 0.39


def test_mmr_lambda_one_is_pure_relevance_order() -> None:
    out = mmr_rerank(_ABC, lambda_=1.0)
    assert [it.id for it in out] == ["A", "B", "C"]
    # With lambda_=1.0 the redundancy term vanishes: score == normalized relevance.
    assert [it.score for it in out] == [1.0, 0.9, 0.8]


def test_mmr_k_truncates_selection() -> None:
    out = mmr_rerank(_ABC, k=2)
    assert len(out) == 2
    assert [it.id for it in out] == ["A", "C"]
    assert [it.rank for it in out] == [0, 1]


def test_evidence_boost_lifts_high_quality_candidate() -> None:
    # Q is marginally more relevant, but P has far stronger evidence.
    p = {
        "id": "P",
        "score": 0.60,
        "node": {"evidence_strength": "peer_reviewed", "confidence": 0.9, "verified": True},
    }
    q = {
        "id": "Q",
        "score": 0.62,
        "node": {"evidence_strength": "unverified", "confidence": 0.3},
    }
    # Without the boost, Q outranks P.
    assert [c["id"] for c in sorted([p, q], key=lambda c: -c["score"])] == ["Q", "P"]
    out = evidence_boost_rerank([q, p], weight=0.2)
    assert [it.id for it in out] == ["P", "Q"]
    # eq(P) = 1.0 (0.7*1.0 + 0.3*0.9 = 0.97, +0.1 verified → clipped to 1.0);
    # eq(Q) = 0.30 (0.7*0.3 + 0.3*0.3).
    #   P: 0.60 + 0.2*1.0  = 0.80
    #   Q: 0.62 + 0.2*0.30 = 0.68
    assert out[0].score == 0.8
    assert out[1].score == 0.68
    assert out[0].base_score == 0.6


def test_evidence_boost_zero_weight_preserves_relevance_order() -> None:
    p = {"id": "P", "score": 0.60, "node": {"evidence_strength": "peer_reviewed"}}
    q = {"id": "Q", "score": 0.62, "node": {"evidence_strength": "unverified"}}
    out = evidence_boost_rerank([p, q], weight=0.0)
    # weight 0 → no nudge, pure relevance order (Q above P), ids preserved.
    assert [it.id for it in out] == ["Q", "P"]
    assert {it.id for it in out} == {"P", "Q"}
    assert out[0].score == 0.62
    assert out[1].score == 0.6


def test_evidence_boost_singleton_and_default_node() -> None:
    # No 'node' key → evidence_quality_score falls back to defaults (eq = 0.39).
    out = evidence_boost_rerank([{"id": "solo", "score": 0.5}])
    assert len(out) == 1
    assert out[0].id == "solo"
    assert out[0].rank == 0
    # 0.5 + 0.2*0.39 = 0.578
    assert out[0].score == 0.578


def test_reranked_item_as_dict_roundtrip() -> None:
    item = RerankedItem(id="x", score=0.5, base_score=0.4, rank=2, reason="mmr")
    assert item.as_dict() == {
        "id": "x",
        "score": 0.5,
        "base_score": 0.4,
        "rank": 2,
        "reason": "mmr",
    }
    # Frozen: attributes are immutable.
    try:
        item.score = 0.9  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - only runs if dataclass is not frozen
        raise AssertionError("RerankedItem must be frozen")
