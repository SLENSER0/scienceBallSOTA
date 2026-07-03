"""Tests for gap-ranking quality eval (§15.10 / §18.6).

Ручные проверки: значения nDCG и Spearman посчитаны из формул DCG = sum(rel/log2(i+2)) и
rho = 1 - 6*sum(d^2)/(n(n^2-1)) для маленьких, проверяемых вручную примеров.
"""

from __future__ import annotations

from math import isclose, log2

from kg_eval.gap_ranking_eval import (
    GapRankingScore,
    _dcg,
    evaluate,
    ndcg_at_k,
    spearman,
)

# Golden priority: релевантности убывают a > b > c > d.
GOLD_REL = {"a": 3.0, "b": 2.0, "c": 1.0, "d": 0.0}
GOLD_ORDER = ["a", "b", "c", "d"]


def test_dcg_matches_manual() -> None:
    # DCG([3,2,1]) = 3/log2(2) + 2/log2(3) + 1/log2(4)
    expected = 3 / log2(2) + 2 / log2(3) + 1 / log2(4)
    assert isclose(_dcg([3.0, 2.0, 1.0]), expected)


def test_perfect_order_ndcg_is_one() -> None:
    # (1) predicted == relevance-descending order -> nDCG == 1.0
    predicted = ["a", "b", "c", "d"]
    assert isclose(ndcg_at_k(predicted, GOLD_REL), 1.0)


def test_reversed_ndcg_below_one_and_spearman_minus_one() -> None:
    # (2) fully reversed -> nDCG < 1.0 and Spearman == -1.0
    predicted = ["d", "c", "b", "a"]
    assert ndcg_at_k(predicted, GOLD_REL) < 1.0
    assert isclose(spearman(predicted, GOLD_ORDER), -1.0)


def test_identical_order_spearman_is_one() -> None:
    # (3) identical order -> Spearman == 1.0
    predicted = ["a", "b", "c", "d"]
    assert isclose(spearman(predicted, GOLD_ORDER), 1.0)


def test_k_truncates_ndcg() -> None:
    # (4) k truncates: only top-k contribute. With k=1 a perfect first pick scores 1.0
    # even though the rest of the order is wrong.
    predicted = ["a", "d", "c", "b"]
    assert isclose(ndcg_at_k(predicted, GOLD_REL, k=1), 1.0)
    # ideal top-1 gain = 3 (a); predicted top-1 gain = 3 (a) -> dcg == idcg
    # but full order (k=4) is imperfect -> < 1.0
    assert ndcg_at_k(predicted, GOLD_REL, k=4) < 1.0


def test_ids_absent_from_gold_relevance_contribute_zero() -> None:
    # (5) unknown ids get relevance 0. Placing an unknown id first hurts nDCG.
    predicted = ["zzz", "a", "b", "c"]
    # dcg = 0/log2(2) + 3/log2(3) + 2/log2(4) + 1/log2(5)
    dcg = 0.0 + 3 / log2(3) + 2 / log2(4) + 1 / log2(5)
    idcg = 3 / log2(2) + 2 / log2(3) + 1 / log2(4) + 0.0
    assert isclose(ndcg_at_k(predicted, GOLD_REL), dcg / idcg)
    assert ndcg_at_k(predicted, GOLD_REL) < 1.0


def test_empty_predicted() -> None:
    # (6) empty predicted -> nDCG 0.0, n_matched 0
    score = evaluate([], GOLD_REL, GOLD_ORDER)
    assert score.ndcg_at_k == 0.0
    assert score.n_matched == 0
    assert score.spearman == 0.0


def test_all_equal_relevance_ndcg_one() -> None:
    # (7) all-equal relevance -> any order is ideal -> nDCG 1.0
    flat = {"a": 1.0, "b": 1.0, "c": 1.0}
    assert isclose(ndcg_at_k(["c", "a", "b"], flat), 1.0)
    assert isclose(ndcg_at_k(["b", "c", "a"], flat), 1.0)


def test_as_dict_exposes_all_fields() -> None:
    # (8) as_dict exposes all four fields; ndcg in [0, 1]
    score = evaluate(["a", "b", "c", "d"], GOLD_REL, GOLD_ORDER)
    d = score.as_dict()
    assert set(d) == {"ndcg_at_k", "spearman", "k", "n_matched"}
    assert 0.0 <= d["ndcg_at_k"] <= 1.0
    assert isinstance(score, GapRankingScore)


def test_all_zero_relevance_ndcg_zero() -> None:
    # ideal DCG is 0 -> guard returns 0.0
    assert ndcg_at_k(["a", "b"], {"a": 0.0, "b": 0.0}) == 0.0


def test_spearman_single_common_id_is_zero() -> None:
    # fewer than two common ids -> 0.0 (undefined correlation)
    assert spearman(["a", "x"], ["a", "y"]) == 0.0


def test_spearman_partial_overlap_matched_only() -> None:
    # only b, c, d are common; predicted keeps them in gold order -> rho == 1.0
    predicted = ["zzz", "b", "c", "d"]
    assert isclose(spearman(predicted, ["b", "c", "d"]), 1.0)


def test_evaluate_n_matched_counts_common_ids() -> None:
    score = evaluate(["a", "b", "unknown"], GOLD_REL, GOLD_ORDER)
    assert score.n_matched == 2
    assert score.k == 10
