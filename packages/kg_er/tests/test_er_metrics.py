"""ER quality-metric tests (§8.12 eval / §8.13 observability).

Hand-checkable clusterings: a fixed partial-overlap case exercises pairwise,
purity and B³ with pen-and-paper expected values, plus the three corner cases
(perfect / all-singletons / all-merged) and a ResolveResult extraction path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from kg_er.metrics import (
    ERMetrics,
    all_metrics,
    b_cubed_precision_recall_f1,
    cluster_purity,
    inverse_purity,
    metrics_from_resolve_result,
    pairwise_precision_recall_f1,
)

# Reference partial-overlap case used across several tests.
#   gold:      {a,b,c} {d,e} {f}
#   predicted: {a,b}   {c,d} {e,f}
# N = 6 items. Worked out by hand in each test below.
GOLD = [{"a", "b", "c"}, {"d", "e"}, {"f"}]
PRED = [{"a", "b"}, {"c", "d"}, {"e", "f"}]


# ---- corner case 1: perfect clustering -> every metric 1.0 ----------------
def test_perfect_clustering_all_metrics_one() -> None:
    gold = [["m1", "m2", "m3"], ["m4", "m5"], ["m6"]]
    pred = [["m3", "m2", "m1"], ["m5", "m4"], ["m6"]]  # same partition, reordered
    m = all_metrics(pred, gold)
    assert m.pairwise.precision == 1.0 and m.pairwise.recall == 1.0
    assert m.pairwise.f1 == 1.0
    assert m.b_cubed.precision == 1.0 and m.b_cubed.recall == 1.0 and m.b_cubed.f1 == 1.0
    assert m.purity == 1.0 and m.inverse_purity == 1.0
    assert (m.n_items, m.n_predicted_clusters, m.n_gold_clusters) == (6, 3, 3)


# ---- corner case 2: all-singletons prediction -----------------------------
def test_all_singletons_prediction() -> None:
    pred = [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]]
    pw = pairwise_precision_recall_f1(pred, GOLD)
    # no predicted pairs: precision is vacuously 1.0, recall 0, F1 0.
    assert pw.precision == 1.0 and pw.recall == 0.0 and pw.f1 == 0.0
    # every singleton is 100% pure; B³ precision is likewise 1.0.
    assert cluster_purity(pred, GOLD) == 1.0
    b3 = b_cubed_precision_recall_f1(pred, GOLD)
    assert b3.precision == 1.0
    # recall = mean(1/|G(i)|) = (3·1/3 + 2·1/2 + 1·1)/6 = 3/6 = 0.5
    assert b3.recall == pytest.approx(0.5)
    # inverse purity = (max 1 per gold cluster) · 3 / 6 = 0.5
    assert inverse_purity(pred, GOLD) == pytest.approx(0.5)


# ---- corner case 3: all-merged prediction ---------------------------------
def test_all_merged_prediction() -> None:
    pred = [["a", "b", "c", "d", "e", "f"]]
    pw = pairwise_precision_recall_f1(pred, GOLD)
    # gold pairs = C(3,2)+C(2,2) = 3+1 = 4 ; predicted pairs = C(6,2) = 15
    assert pw.precision == pytest.approx(4 / 15) and pw.recall == 1.0
    # inverse purity trivially 1.0 (each gold cluster fully inside the one cluster)
    assert inverse_purity(pred, GOLD) == 1.0
    # purity = max gold overlap (3) / 6 = 0.5
    assert cluster_purity(pred, GOLD) == pytest.approx(0.5)
    b3 = b_cubed_precision_recall_f1(pred, GOLD)
    assert b3.recall == 1.0
    # precision = mean(|G(i)|/6) = (3·3 + 2·2 + 1·1)/36 = 14/36 = 7/18
    assert b3.precision == pytest.approx(7 / 18)


# ---- partial overlap: pairwise, hand-computed -----------------------------
def test_partial_overlap_pairwise() -> None:
    pw = pairwise_precision_recall_f1(PRED, GOLD)
    # predicted pairs {ab, cd, ef}=3 ; gold pairs {ab, ac, bc, de}=4 ; TP={ab}=1
    assert pw.precision == pytest.approx(1 / 3)
    assert pw.recall == pytest.approx(1 / 4)
    assert pw.f1 == pytest.approx(2 / 7)  # 2PR/(P+R) = 2·(1/12)/(7/12)


# ---- partial overlap: purity / inverse purity, hand-computed --------------
def test_partial_overlap_purity() -> None:
    # purity: max gold overlap per predicted cluster = 2 (ab⊂G1) +1 +1 = 4 /6
    assert cluster_purity(PRED, GOLD) == pytest.approx(4 / 6)
    # inverse purity: max pred overlap per gold cluster = 2 (ab in P1) +1 +1 = 4 /6
    assert inverse_purity(PRED, GOLD) == pytest.approx(4 / 6)


# ---- partial overlap: B³, hand-computed -----------------------------------
def test_partial_overlap_b_cubed() -> None:
    b3 = b_cubed_precision_recall_f1(PRED, GOLD)
    # per-item precision: a,b=1 ; c,d,e,f=1/2 -> mean = 4/6 = 2/3
    assert b3.precision == pytest.approx(2 / 3)
    # per-item recall: a,b=2/3 ; c=1/3 ; d,e=1/2 ; f=1 -> sum 11/3, mean 11/18
    assert b3.recall == pytest.approx(11 / 18)
    # F1 = 2·(2/3)·(11/18) / (2/3 + 11/18) = 44/69
    assert b3.f1 == pytest.approx(44 / 69)


# ---- B³ sanity: over-split lifts precision, over-merge lifts recall -------
def test_b_cubed_sanity_split_vs_merge() -> None:
    singletons = [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]]
    merged = [["a", "b", "c", "d", "e", "f"]]
    split_b3 = b_cubed_precision_recall_f1(singletons, GOLD)
    merge_b3 = b_cubed_precision_recall_f1(merged, GOLD)
    # over-splitting: perfect precision, imperfect recall
    assert split_b3.precision == 1.0 and split_b3.recall < 1.0
    # over-merging: perfect recall, imperfect precision (mirror image)
    assert merge_b3.recall == 1.0 and merge_b3.precision < 1.0
    # the correct partition beats both on F1
    perfect_b3 = b_cubed_precision_recall_f1(GOLD, GOLD)
    assert perfect_b3.f1 == 1.0
    assert perfect_b3.f1 > split_b3.f1 and perfect_b3.f1 > merge_b3.f1


# ---- ResolveResult extraction path (ClusterResult.members) ----------------
def test_metrics_from_resolve_result_perfect() -> None:
    # Duck-typed like kg_er.pipeline.ResolveResult: .clusters -> objects with
    # .members (see base.ClusterResult). Predicted == gold -> all metrics 1.0.
    clusters = [
        SimpleNamespace(members=("m1", "m2", "m3")),
        SimpleNamespace(members=("m4", "m5")),
    ]
    result = SimpleNamespace(clusters=clusters)
    gold = [{"m1", "m2", "m3"}, {"m4", "m5"}]
    m = metrics_from_resolve_result(result, gold)
    assert isinstance(m, ERMetrics)
    assert m.pairwise.f1 == 1.0 and m.b_cubed.f1 == 1.0
    assert m.purity == 1.0 and m.inverse_purity == 1.0
    assert m.n_items == 5


def test_metrics_from_resolve_result_missing_singletons() -> None:
    # Splink-style result: lists only the merged pair; m3 is absent but present
    # in gold as a singleton -> universe = {m1,m2,m3}, still scored correctly.
    result = SimpleNamespace(clusters=[SimpleNamespace(members=("m1", "m2"))])
    gold = [["m1", "m2"], ["m3"]]
    m = metrics_from_resolve_result(result, gold)
    assert m.n_items == 3
    # predicted {m1,m2}{m3(implicit)} == gold -> perfect
    assert m.pairwise.f1 == 1.0 and m.b_cubed.f1 == 1.0


# ---- as_dict serialisation shape (§8.13 /admin/metrics export) ------------
def test_as_dict_serialisation() -> None:
    m = all_metrics(PRED, GOLD)
    d = m.as_dict()
    assert set(d) == {
        "pairwise",
        "b_cubed",
        "purity",
        "inverse_purity",
        "n_items",
        "n_predicted_clusters",
        "n_gold_clusters",
    }
    assert set(d["pairwise"]) == {"precision", "recall", "f1"}
    assert d["pairwise"]["precision"] == pytest.approx(1 / 3, abs=1e-6)
    assert d["n_items"] == 6


# ---- empty inputs are well-defined ----------------------------------------
def test_empty_inputs_are_perfect() -> None:
    m = all_metrics([], [])
    assert m.pairwise.f1 == 1.0 and m.b_cubed.f1 == 1.0
    assert m.purity == 1.0 and m.inverse_purity == 1.0
    assert m.n_items == 0
