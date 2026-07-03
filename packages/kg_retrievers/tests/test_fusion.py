"""Hand-checked tests for spec-exact §12.4/§10.2 fusion (RRF + weighted).

Каждое ожидаемое число посчитано вручную по формулам §10.2/§7.5 Node 6.
"""

from __future__ import annotations

import pytest

from kg_retrievers.fusion import (
    DEFAULT_FUSION_WEIGHTS,
    FusedHit,
    rrf_fuse,
    validate_weights,
    weighted_fuse_v2,
)

# ---------------------------------------------------------------------------
# RRF — Reciprocal Rank Fusion (score = Σ 1/(k+rank), rank 1-based, k=60)
# ---------------------------------------------------------------------------


def test_rrf_reference_number_rank1_in_two_lists() -> None:
    """Id ranked #1 in two channels → 1/61 + 1/61 = 2/61 ≈ 0.0327868852."""
    rankings = {"dense": ["doc1", "doc2"], "bm25": ["doc1", "doc3"]}
    ranked = rrf_fuse(rankings, k=60)
    scores = dict(ranked)
    assert abs(scores["doc1"] - 2.0 / 61.0) < 1e-6
    assert abs(scores["doc1"] - 0.0327868852) < 1e-6
    assert ranked[0][0] == "doc1"  # highest → first


def test_rrf_single_channel_reference_numbers() -> None:
    """One channel: score = 1/(60+rank) для rank 1,2,3 → 1/61, 1/62, 1/63."""
    ranked = rrf_fuse({"dense": ["x", "y", "z"]}, k=60)
    assert [cid for cid, _ in ranked] == ["x", "y", "z"]
    scores = dict(ranked)
    assert abs(scores["x"] - 1.0 / 61.0) < 1e-9
    assert abs(scores["y"] - 1.0 / 62.0) < 1e-9
    assert abs(scores["z"] - 1.0 / 63.0) < 1e-9


def test_rrf_ordering_two_channels() -> None:
    """b appears high in both channels → outranks a/c that appear once each."""
    rankings = {"dense": ["a", "b", "c"], "bm25": ["b", "c", "a"]}
    # a: 1/61 + 1/63; b: 1/62 + 1/61; c: 1/63 + 1/62
    ranked = rrf_fuse(rankings, k=60)
    scores = dict(ranked)
    # a≈0.0322665, b≈0.0325225, c≈0.0320020 → b > a > c
    assert abs(scores["a"] - (1 / 61 + 1 / 63)) < 1e-12
    assert abs(scores["b"] - (1 / 62 + 1 / 61)) < 1e-12
    assert abs(scores["c"] - (1 / 63 + 1 / 62)) < 1e-12
    assert scores["b"] > scores["a"] > scores["c"]
    assert [cid for cid, _ in ranked] == ["b", "a", "c"]


def test_rrf_empty_returns_empty_list() -> None:
    """No rankings (and empty channels) → []."""
    assert rrf_fuse({}) == []
    assert rrf_fuse({"dense": [], "bm25": []}) == []


def test_rrf_tie_stability_symmetric() -> None:
    """Symmetric ranks → equal scores; порядок первого появления сохраняется."""
    rankings = {"dense": ["x", "y"], "bm25": ["y", "x"]}
    ranked = rrf_fuse(rankings, k=60)
    # both = 1/61 + 1/62 exactly equal → stable order = first appearance [x, y]
    assert ranked[0][1] == pytest.approx(ranked[1][1])
    assert [cid for cid, _ in ranked] == ["x", "y"]


def test_rrf_rejects_nonpositive_k() -> None:
    """k must be positive (1/(k+rank) требует k>0)."""
    with pytest.raises(ValueError):
        rrf_fuse({"dense": ["a"]}, k=0)


# ---------------------------------------------------------------------------
# weighted_fuse_v2 — §10.2 formula EXACTLY
# ---------------------------------------------------------------------------


def test_weighted_fuse_v2_hand_computed() -> None:
    """0.35*0.8 + 0.25*0.6 + 0.20*0.4 + 0.10*1.0 + 0.10*0.5 = 0.66 (hand-checked)."""
    channel_scores = {
        "dense": {"d1": 0.8, "d2": 0.2},
        "sparse": {"d1": 0.6, "d2": 0.1},
        "bm25": {"d1": 0.4, "d2": 0.0},
        "graph_proximity": {"d1": 1.0, "d2": 0.0},
        "evidence_quality": {"d1": 0.5, "d2": 1.0},
    }
    ranked = weighted_fuse_v2(channel_scores)
    by_id = {h.id: h for h in ranked}
    # d1: 0.28 + 0.15 + 0.08 + 0.10 + 0.05 = 0.66
    assert by_id["d1"].score == pytest.approx(0.66, abs=1e-9)
    # d2: 0.35*0.2 + 0.25*0.1 + 0 + 0 + 0.10*1.0 = 0.07 + 0.025 + 0.10 = 0.195
    assert by_id["d2"].score == pytest.approx(0.195, abs=1e-9)
    assert ranked[0].id == "d1"  # 0.66 > 0.195
    assert by_id["d1"].components["graph_proximity"] == 1.0


def test_weighted_fuse_v2_missing_component_is_zero() -> None:
    """Document present only in some channels → missing components count as 0."""
    channel_scores = {"dense": {"only": 1.0}}
    ranked = weighted_fuse_v2(channel_scores)
    assert len(ranked) == 1
    hit = ranked[0]
    # score = 0.35*1.0 + 0 + 0 + 0 + 0 = 0.35
    assert hit.score == pytest.approx(0.35, abs=1e-12)
    assert hit.components == {
        "dense": 1.0,
        "sparse": 0.0,
        "bm25": 0.0,
        "graph_proximity": 0.0,
        "evidence_quality": 0.0,
    }


def test_weighted_fuse_v2_empty_returns_empty_list() -> None:
    """No channel scores → []."""
    assert weighted_fuse_v2({}) == []


def test_weighted_fuse_v2_tie_stability() -> None:
    """Equal fused scores keep first-appearance order (stable)."""
    channel_scores = {"dense": {"a": 0.5, "b": 0.5}}
    ranked = weighted_fuse_v2(channel_scores)
    assert ranked[0].score == pytest.approx(ranked[1].score)
    assert [h.id for h in ranked] == ["a", "b"]


def test_weighted_fuse_v2_dense_weight_changes_order() -> None:
    """Raising sparse over dense predictably reorders the two candidates (§12.4 c)."""
    channel_scores = {"dense": {"A": 1.0, "B": 0.0}, "sparse": {"A": 0.0, "B": 1.0}}
    # Default: A = 0.35, B = 0.25 → A first.
    assert weighted_fuse_v2(channel_scores)[0].id == "A"
    reweighted = {
        "dense": 0.20,
        "sparse": 0.40,
        "bm25": 0.20,
        "graph_proximity": 0.10,
        "evidence_quality": 0.10,
    }
    validate_weights(reweighted)  # still sums to 1.0
    # Now A = 0.20, B = 0.40 → B first.
    assert weighted_fuse_v2(channel_scores, reweighted)[0].id == "B"


def test_fused_hit_as_dict_roundtrip() -> None:
    """as_dict() exposes id/score/components as a plain dict copy (house style)."""
    hit = FusedHit(id="d1", score=0.66, components={"dense": 0.8})
    d = hit.as_dict()
    assert d == {"id": "d1", "score": 0.66, "components": {"dense": 0.8}}
    d["components"]["dense"] = 0.0  # copy → original untouched
    assert hit.components["dense"] == 0.8


# ---------------------------------------------------------------------------
# validate_weights + DEFAULT_FUSION_WEIGHTS invariants (§10.2 / §12.4)
# ---------------------------------------------------------------------------


def test_default_weights_sum_to_one() -> None:
    """§10.2 defaults: 0.35+0.25+0.20+0.10+0.10 = 1.0 exactly (within tol)."""
    assert sum(DEFAULT_FUSION_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)
    assert DEFAULT_FUSION_WEIGHTS == {
        "dense": 0.35,
        "sparse": 0.25,
        "bm25": 0.20,
        "graph_proximity": 0.10,
        "evidence_quality": 0.10,
    }
    validate_weights(DEFAULT_FUSION_WEIGHTS)  # must not raise


def test_validate_weights_rejects_sum_0_9() -> None:
    """Weights summing to 0.9 violate §12.4 invariant → ValueError."""
    bad = {
        "dense": 0.35,
        "sparse": 0.25,
        "bm25": 0.20,
        "graph_proximity": 0.10,
        "evidence_quality": 0.0,
    }
    assert sum(bad.values()) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        validate_weights(bad)


def test_validate_weights_rejects_overweight_and_empty() -> None:
    """Sum > 1.0 (1.1) and empty weights both raise."""
    with pytest.raises(ValueError):
        validate_weights({"dense": 0.7, "sparse": 0.4})  # 1.1
    with pytest.raises(ValueError):
        validate_weights({})


def test_validate_weights_accepts_tiny_float_drift() -> None:
    """Three thirds (0.333.. *3) drift < 1e-6 from 1.0 → accepted."""
    validate_weights({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
