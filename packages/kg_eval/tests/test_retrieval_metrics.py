"""Retrieval ranking metrics — recall@k/precision@k/hit@k/MRR/nDCG/AP (§18.6/§15.2)."""

from __future__ import annotations

import math

from pytest import approx

from kg_eval.retrieval_metrics import (
    aggregate,
    average_precision,
    evaluate,
    hit_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

# log2(3) discount used repeatedly in hand-checked nDCG expectations.
_D2 = 1.0 / math.log2(3)  # gain at rank 2 ≈ 0.63093
_D3 = 1.0 / math.log2(4)  # gain at rank 3 = 0.5


def test_perfect_ranking_scores_all_one() -> None:
    ranked = ["a", "b", "c"]
    golden = {"a", "b", "c"}
    assert recall_at_k(ranked, golden, 3) == 1.0
    assert precision_at_k(ranked, golden, 3) == 1.0
    assert hit_at_k(ranked, golden, 3) == 1.0
    assert mrr(ranked, golden) == 1.0
    assert ndcg_at_k(ranked, golden, 3) == 1.0
    assert average_precision(ranked, golden) == 1.0


def test_partial_ranking_hand_computed() -> None:
    # ranked: a(rel) x b(rel) y ; golden = {a, b, c} (c never retrieved).
    ranked = ["a", "x", "b", "y"]
    golden = {"a", "b", "c"}
    assert recall_at_k(ranked, golden, 4) == approx(2 / 3)  # 2 of 3 relevant seen
    assert precision_at_k(ranked, golden, 4) == 0.5  # 2 hits / 4 retrieved
    assert hit_at_k(ranked, golden, 4) == 1.0
    assert mrr(ranked, golden) == 1.0  # first relevant at rank 1
    # DCG = 1/log2(2) + 1/log2(4) = 1 + 0.5 ; IDCG over 3 ideal hits.
    idcg = 1.0 + _D2 + _D3
    assert ndcg_at_k(ranked, golden, 4) == approx((1.0 + _D3) / idcg)
    assert average_precision(ranked, golden) == approx(5 / 9)  # (1/1 + 2/3) / 3


def test_empty_golden_edge_conventions() -> None:
    ranked = ["a", "b"]
    empty: set[str] = set()
    assert recall_at_k(ranked, empty, 5) == 1.0  # vacuously complete
    assert precision_at_k(ranked, empty, 5) == 0.0
    assert hit_at_k(ranked, empty, 5) == 0.0
    assert mrr(ranked, empty) == 0.0
    assert ndcg_at_k(ranked, empty, 5) == 0.0
    assert average_precision(ranked, empty) == 0.0


def test_empty_ranked_list() -> None:
    empty: list[str] = []
    golden = {"a"}
    assert recall_at_k(empty, golden, 5) == 0.0
    assert precision_at_k(empty, golden, 5) == 0.0
    assert hit_at_k(empty, golden, 5) == 0.0
    assert mrr(empty, golden) == 0.0
    assert ndcg_at_k(empty, golden, 5) == 0.0
    assert average_precision(empty, golden) == 0.0


def test_k_larger_than_list() -> None:
    # k=5 but only 2 retrieved; both relevant → everything perfect, no ZeroDiv.
    ranked = ["a", "b"]
    assert recall_at_k(ranked, {"a", "b"}, 5) == 1.0
    assert precision_at_k(ranked, {"a", "b"}, 5) == 1.0  # denom = min(5, 2) = 2
    assert ndcg_at_k(ranked, {"a", "b"}, 5) == 1.0
    assert average_precision(ranked, {"a", "b"}) == 1.0
    # recall divides by |relevant|, not by k, so a missing golden id lowers it.
    assert recall_at_k(ranked, {"a", "b", "c"}, 5) == approx(2 / 3)


def test_precision_denominator_capped_to_retrieved() -> None:
    # Single retrieved id, relevant, huge k → precision 1.0 (not 1/10).
    assert precision_at_k(["a"], {"a"}, 10) == 1.0
    # Three retrieved, one relevant → 1/3 regardless of k=10.
    assert precision_at_k(["a", "x", "y"], {"a"}, 10) == approx(1 / 3)


def test_mrr_position_sensitivity() -> None:
    golden = {"a"}
    r1 = mrr(["a", "x", "y"], golden)
    r2 = mrr(["x", "a", "y"], golden)
    r3 = mrr(["x", "y", "a"], golden)
    r4 = mrr(["x", "y", "z"], golden)
    assert (r1, r2, r3, r4) == (1.0, 0.5, approx(1 / 3), 0.0)
    assert r1 > r2 > r3 > r4  # strictly rewards earlier hits


def test_ndcg_monotonic_in_position() -> None:
    golden = {"a"}
    n1 = ndcg_at_k(["a", "x", "y"], golden, 3)
    n2 = ndcg_at_k(["x", "a", "y"], golden, 3)
    n3 = ndcg_at_k(["x", "y", "a"], golden, 3)
    assert n1 == 1.0
    assert n2 == approx(_D2)  # (1/log2 3) / (1/log2 2)
    assert n3 == approx(_D3)  # 0.5
    assert n1 > n2 > n3
    # cutoff: relevant id beyond k contributes nothing.
    assert ndcg_at_k(["x", "y", "a"], golden, 2) == 0.0


def test_ndcg_better_ranking_scores_higher() -> None:
    golden = {"a", "b"}
    ideal = ndcg_at_k(["a", "b", "x", "y"], golden, 4)
    worse = ndcg_at_k(["x", "a", "y", "b"], golden, 4)
    assert ideal == 1.0
    # DCG_worse = 1/log2(3) + 1/log2(5) ; IDCG = 1 + 1/log2(3).
    dcg_worse = _D2 + 1.0 / math.log2(5)
    idcg = 1.0 + _D2
    assert worse == approx(dcg_worse / idcg)
    assert ideal > worse


def test_average_precision_hand_values() -> None:
    golden = {"a", "b"}
    # a x b → (1/1 + 2/3) / 2 = 5/6
    assert average_precision(["a", "x", "b"], golden) == approx(5 / 6)
    # x a b → (1/2 + 2/3) / 2 = 7/12
    assert average_precision(["x", "a", "b"], golden) == approx(7 / 12)


def test_duplicates_collapsed_before_scoring() -> None:
    # Without dedup, [a, a] would count 'a' twice → recall 1.0 (wrong).
    assert recall_at_k(["a", "a"], {"a", "b"}, 2) == 0.5
    assert precision_at_k(["a", "a"], {"a", "b"}, 2) == 1.0  # top = [a], 1/1
    assert hit_at_k(["a", "a"], {"a", "b"}, 2) == 1.0


def test_evaluate_bundle_and_as_dict_rounding() -> None:
    m = evaluate(["a", "x", "b", "y"], {"a", "b", "c"}, k=4)
    assert m.k == 4
    assert m.recall_at_k == approx(2 / 3)
    d = m.as_dict()
    assert set(d) == {
        "k",
        "recall_at_k",
        "precision_at_k",
        "hit_at_k",
        "mrr",
        "ndcg_at_k",
        "average_precision",
    }
    assert d["k"] == 4
    assert d["recall_at_k"] == round(2 / 3, 4) == 0.6667
    assert d["precision_at_k"] == 0.5


def test_aggregate_over_multiple_queries() -> None:
    runs = [
        (["a", "b", "c"], {"a", "b", "c"}),  # perfect
        (["x", "a"], {"a"}),  # relevant at rank 2
    ]
    agg = aggregate(runs, k=2)
    assert agg.k == 2
    # run1@2: recall 2/3, prec 1.0, ndcg 1.0, mrr 1.0, ap(full) 1.0
    # run2@2: recall 1.0, prec 0.5, ndcg _D2, mrr 0.5, ap(full) 0.5
    assert agg.recall_at_k == approx((2 / 3 + 1.0) / 2)  # 5/6
    assert agg.precision_at_k == 0.75
    assert agg.hit_at_k == 1.0
    assert agg.mrr == 0.75  # (1.0 + 0.5) / 2
    assert agg.ndcg_at_k == approx((1.0 + _D2) / 2)
    assert agg.average_precision == 0.75  # MAP = (1.0 + 0.5) / 2


def test_aggregate_empty_runs_is_zero() -> None:
    agg = aggregate([], k=10)
    assert agg.k == 10
    assert agg.as_dict() == {
        "k": 10,
        "recall_at_k": 0.0,
        "precision_at_k": 0.0,
        "hit_at_k": 0.0,
        "mrr": 0.0,
        "ndcg_at_k": 0.0,
        "average_precision": 0.0,
    }
