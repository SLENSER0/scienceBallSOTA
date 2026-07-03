"""Candidate generation + DTO tests (§8.8). Pure Python, hand-checked, no Splink."""

from __future__ import annotations

import pytest
from kg_er.candidate import (
    Candidate,
    build_candidates,
    decide,
    generate_pairs,
)

# 6 records in 3 blocks: X={a,b,c}, Y={d,e}, Z={f}. Hand-checkable throughout.
RECS = [
    {"id": "a", "blk": "X"},
    {"id": "b", "blk": "X"},
    {"id": "c", "blk": "X"},
    {"id": "d", "blk": "Y"},
    {"id": "e", "blk": "Y"},
    {"id": "f", "blk": "Z"},  # singleton block — contributes no pair
]
# X: a-b, a-c, b-c (3) + Y: d-e (1) + Z: none = 4 pairs total.
EXPECTED = {("a", "b"), ("a", "c"), ("b", "c"), ("d", "e")}


# ---- decide bands --------------------------------------------------------
def test_decide_bands() -> None:
    assert decide(0.95) == "auto_merge"
    assert decide(0.7) == "review"
    assert decide(0.3) == "reject"


def test_decide_thresholds_inclusive() -> None:
    # exact threshold lands in the higher band (>= semantics)
    assert decide(0.9) == "auto_merge"
    assert decide(0.6) == "review"
    assert decide(0.5999) == "reject"
    # custom thresholds are honored
    assert decide(0.55, auto=0.8, review=0.5) == "review"
    assert decide(0.85, auto=0.8, review=0.5) == "auto_merge"


# ---- generate_pairs: blocking ------------------------------------------
def test_generate_pairs_same_block_only() -> None:
    pairs = generate_pairs(RECS, block_key="blk")
    blk = {r["id"]: r["blk"] for r in RECS}
    assert set(pairs) == EXPECTED
    # every emitted pair shares a block; the singleton 'f' never appears
    assert all(blk[left] == blk[right] for left, right in pairs)
    assert not any("f" in pair for pair in pairs)


def test_blocking_cuts_pair_count() -> None:
    pairs = generate_pairs(RECS, block_key="blk")
    full_cross = len(RECS) * (len(RECS) - 1) // 2  # 6*5/2 = 15
    assert full_cross == 15
    assert len(pairs) == 4
    assert len(pairs) < full_cross  # blocking strictly reduces comparisons


def test_generate_pairs_symmetric_dedup() -> None:
    pairs = generate_pairs(RECS, block_key="blk")
    forward = set(pairs)
    reversed_input = set(generate_pairs(list(reversed(RECS)), block_key="blk"))
    # (a,b) == (b,a): input order does not change the canonical pair set
    assert forward == reversed_input == EXPECTED
    # canonical ordering + no reversed duplicate present
    assert all(left <= right for left, right in pairs)
    assert not any((right, left) in forward for left, right in pairs if left != right)


def test_generate_pairs_callable_block_key() -> None:
    by_str = generate_pairs(RECS, block_key="blk")
    by_fn = generate_pairs(RECS, block_key=lambda r: r["blk"])
    assert set(by_fn) == set(by_str) == EXPECTED


def test_generate_pairs_skips_missing_block_and_empty() -> None:
    assert generate_pairs([], block_key="blk") == []
    # records with no block value are unblockable -> never paired
    recs = [{"id": "a"}, {"id": "b"}, {"id": "c", "blk": "K"}, {"id": "d", "blk": "K"}]
    assert set(generate_pairs(recs, block_key="blk")) == {("c", "d")}


def test_generate_pairs_uses_unique_id_field() -> None:
    recs = [{"unique_id": "u1", "blk": "Q"}, {"unique_id": "u2", "blk": "Q"}]
    assert generate_pairs(recs, block_key="blk") == [("u1", "u2")]


# ---- build_candidates ----------------------------------------------------
def test_build_candidates_attaches_decision() -> None:
    scored = [
        ("a", "b", 0.95, {"name_sim": 0.99}),
        ("c", "d", 0.72, {"name_sim": 0.8}),
        ("e", "f", 0.20, {"name_sim": 0.1}),
    ]
    cands = build_candidates(scored)
    assert [c.decision for c in cands] == ["auto_merge", "review", "reject"]
    assert all(isinstance(c, Candidate) for c in cands)


def test_build_candidates_preserves_features() -> None:
    feats = {"name_sim": 0.91, "formula_match": True, "block": "X"}
    (cand,) = build_candidates([("a", "b", 0.93, feats)])
    assert cand.features == feats
    # frozen DTO holds a copy: mutating the source does not leak in
    feats["name_sim"] = 0.0
    assert cand.features["name_sim"] == 0.91


def test_build_candidates_accepts_triples_and_mappings() -> None:
    # 3-tuple defaults features to {}; mapping form is also accepted
    (triple,) = build_candidates([("a", "b", 0.95)])
    assert triple.features == {} and triple.decision == "auto_merge"
    (mapped,) = build_candidates(
        [{"left_id": "x", "right_id": "y", "score": 0.65, "features": {"k": 1}}]
    )
    assert mapped.decision == "review" and mapped.features == {"k": 1}


def test_build_candidates_empty() -> None:
    assert build_candidates([]) == []


# ---- Candidate DTO -------------------------------------------------------
def test_candidate_as_dict() -> None:
    c = Candidate("a", "b", 0.9512, features={"name_sim": 0.99}, decision="auto_merge")
    assert c.as_dict() == {
        "left_id": "a",
        "right_id": "b",
        "score": 0.9512,
        "features": {"name_sim": 0.99},
        "decision": "auto_merge",
    }


def test_candidate_rejects_bad_decision() -> None:
    with pytest.raises(ValueError):
        Candidate("a", "b", 0.5, decision="merge_now")
