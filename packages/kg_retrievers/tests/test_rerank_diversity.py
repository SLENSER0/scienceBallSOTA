"""Hand-checked tests for result diversification (§12.12): source-cap + MMR.

Каждое ожидаемое значение посчитано вручную по формулам §12.12 (source cap, MMR
``lambda_ * rel - (1 - lambda_) * jaccard``).
"""

from __future__ import annotations

from kg_retrievers.rerank_diversity import (
    DiversityStats,
    diversify,
    mmr_diversity,
    summarize_diversity,
)

# ---------------------------------------------------------------------------
# diversify — source cap (max_per_key) preserving score order, then top_n
# ---------------------------------------------------------------------------

# One document (D1) dominates the top; D2 has a single lower hit.
_DOMINATED = [
    {"id": "a", "doc_id": "D1", "score": 0.90},
    {"id": "b", "doc_id": "D1", "score": 0.85},
    {"id": "c", "doc_id": "D1", "score": 0.80},
    {"id": "d", "doc_id": "D2", "score": 0.70},
    {"id": "e", "doc_id": "D1", "score": 0.60},
]


def test_diversify_caps_dominating_doc() -> None:
    """max_per_key=2 keeps only the two best D1 hits; c and e (3rd/4th D1) drop out."""
    out = diversify(_DOMINATED, key="doc_id", max_per_key=2)
    assert [h["id"] for h in out] == ["a", "b", "d"]
    # D1 appears exactly twice (capped), D2 once — no single doc dominates.
    doc_counts: dict[str, int] = {}
    for h in out:
        doc_counts[h["doc_id"]] = doc_counts.get(h["doc_id"], 0) + 1
    assert doc_counts == {"D1": 2, "D2": 1}


def test_diversify_preserves_score_order_within_cap() -> None:
    """Distinct docs → no cap fires; output is pure descending-score order."""
    hits = [
        {"id": "m", "doc_id": "D2", "score": 0.5},  # input order is NOT by score
        {"id": "h", "doc_id": "D1", "score": 0.9},
        {"id": "l", "doc_id": "D3", "score": 0.7},
    ]
    out = diversify(hits, key="doc_id", max_per_key=2)
    assert [h["id"] for h in out] == ["h", "l", "m"]
    assert [h["score"] for h in out] == [0.9, 0.7, 0.5]


def test_diversify_top_n_truncates() -> None:
    """top_n=3 keeps only the three highest-scored survivors (distinct docs)."""
    hits = [
        {"id": "p", "doc_id": "D1", "score": 0.9},
        {"id": "q", "doc_id": "D2", "score": 0.8},
        {"id": "r", "doc_id": "D3", "score": 0.7},
        {"id": "s", "doc_id": "D4", "score": 0.6},
        {"id": "t", "doc_id": "D5", "score": 0.5},
    ]
    out = diversify(hits, key="doc_id", max_per_key=2, top_n=3)
    assert [h["id"] for h in out] == ["p", "q", "r"]


def test_diversify_all_same_doc_capped() -> None:
    """Every hit from one doc → capped to max_per_key highest-scored hits."""
    hits = [{"id": f"x{i}", "doc_id": "ONLY", "score": 1.0 - i * 0.1} for i in range(5)]
    out = diversify(hits, key="doc_id", max_per_key=2)
    assert [h["id"] for h in out] == ["x0", "x1"]
    assert len(out) == 2


def test_diversify_empty_returns_empty() -> None:
    assert diversify([]) == []


def test_diversify_single_hit() -> None:
    out = diversify([{"id": "solo", "doc_id": "D9", "score": 0.42}])
    assert len(out) == 1
    assert out[0]["id"] == "solo"


def test_diversify_alternate_key_entity() -> None:
    """The cap key is configurable — cap by ``entity`` instead of doc_id (§12.12)."""
    hits = [
        {"id": "1", "entity": "E1", "score": 0.9},
        {"id": "2", "entity": "E1", "score": 0.8},
        {"id": "3", "entity": "E1", "score": 0.7},
        {"id": "4", "entity": "E2", "score": 0.6},
    ]
    out = diversify(hits, key="entity", max_per_key=1)
    assert [h["id"] for h in out] == ["1", "4"]


def test_diversify_missing_key_never_capped() -> None:
    """Hits lacking the source key get unique buckets → never dropped by the cap."""
    hits = [
        {"id": "n1", "score": 0.9},
        {"id": "n2", "score": 0.8},
        {"id": "n3", "score": 0.7},
    ]
    out = diversify(hits, key="doc_id", max_per_key=1)
    assert [h["id"] for h in out] == ["n1", "n2", "n3"]


def test_diversify_returns_independent_copies() -> None:
    """Mutating an output dict must not touch the input hit (dicts are copied)."""
    src = {"id": "z", "doc_id": "D1", "score": 0.5}
    out = diversify([src])
    out[0]["score"] = 99.0
    assert src["score"] == 0.5


# ---------------------------------------------------------------------------
# mmr_diversity — relevance vs novelty on a similarity key
# ---------------------------------------------------------------------------

# A is top; B is a same-cluster near-duplicate of A; C is a novel cluster, less relevant.
_A = {"id": "A", "score": 1.0, "cluster": "x"}
_B = {"id": "B", "score": 0.9, "cluster": "x"}
_C = {"id": "C", "score": 0.8, "cluster": "y"}
_ABC = [_A, _B, _C]


def test_mmr_promotes_novel_lower_scored_hit() -> None:
    """Default lambda_=0.7 lifts the novel C above the more-relevant duplicate B."""
    out = mmr_diversity(_ABC)
    assert [h["id"] for h in out] == ["A", "C", "B"]
    # Hand-checked marginals (rel max-normalized, max=1.0):
    #   step1 A: 0.7*1.0                         = 0.70  → pick A
    #   step2 B: 0.7*0.9 - 0.3*jaccard({x},{x})  = 0.63 - 0.30 = 0.33
    #         C: 0.7*0.8 - 0.3*jaccard({y},{x})  = 0.56 - 0.00 = 0.56  → pick C
    #   step3 B (only one left)


def test_mmr_lambda_one_is_pure_relevance_order() -> None:
    """lambda_=1.0 zeroes the novelty term → pure descending-relevance order."""
    out = mmr_diversity(_ABC, lambda_=1.0)
    assert [h["id"] for h in out] == ["A", "B", "C"]


def test_mmr_fractional_jaccard_on_feature_sets() -> None:
    """A list-valued similarity key uses Jaccard overlap; novel C still wins slot 2."""
    hits = [
        {"id": "A", "score": 1.0, "cluster": ["water", "membrane"]},
        {"id": "B", "score": 0.9, "cluster": ["water", "membrane", "reverse"]},
        {"id": "C", "score": 0.8, "cluster": ["solar", "tower"]},
    ]
    out = mmr_diversity(hits)
    #   step2 B: 0.7*0.9 - 0.3*(2/3) = 0.63 - 0.20 = 0.43
    #         C: 0.7*0.8 - 0.3*0.0   = 0.56          → pick C (0.56 > 0.43)
    assert [h["id"] for h in out] == ["A", "C", "B"]


def test_mmr_empty_returns_empty() -> None:
    assert mmr_diversity([]) == []


def test_mmr_single_hit() -> None:
    out = mmr_diversity([{"id": "only", "score": 0.5, "cluster": "z"}])
    assert len(out) == 1
    assert out[0]["id"] == "only"


def test_mmr_is_a_reorder_keeping_all_hits() -> None:
    """MMR never drops or duplicates hits — it only reorders the input set."""
    out = mmr_diversity(_ABC, lambda_=0.5)
    assert len(out) == 3
    assert {h["id"] for h in out} == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# summarize_diversity + DiversityStats (explainability, house style)
# ---------------------------------------------------------------------------


def test_summarize_diversity_reports_cap_effect() -> None:
    """Stats over the dominated fixture: 5 in, 3 out, 2 dropped, per-key counts."""
    out = diversify(_DOMINATED, key="doc_id", max_per_key=2)
    stats = summarize_diversity(_DOMINATED, out, key="doc_id")
    assert stats.total_in == 5
    assert stats.total_out == 3
    assert stats.dropped == 2
    assert stats.per_key == {"D1": 2, "D2": 1}


def test_diversity_stats_as_dict_and_frozen() -> None:
    stats = DiversityStats(total_in=5, total_out=3, dropped=2, per_key={"D1": 2})
    assert stats.as_dict() == {
        "total_in": 5,
        "total_out": 3,
        "dropped": 2,
        "per_key": {"D1": 2},
    }
    # as_dict returns a copy → mutating it leaves the frozen instance untouched.
    stats.as_dict()["per_key"]["D1"] = 0
    assert stats.per_key["D1"] == 2
    try:
        stats.total_in = 9  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - only runs if dataclass is not frozen
        raise AssertionError("DiversityStats must be frozen")
