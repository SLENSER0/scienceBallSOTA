"""Pairwise entity-resolution cluster precision/recall/F1 (§18.7)."""

from __future__ import annotations

from pytest import approx

from kg_eval.entity_resolution_eval import (
    ERScores,
    _same_cluster_pairs,
    evaluate_er,
)


def test_same_cluster_pairs_enumerates_intra_cluster_unordered() -> None:
    # [a,b,c] -> {a-b, a-c, b-c}; singleton [d] -> nothing.
    pairs = _same_cluster_pairs([["a", "b", "c"], ["d"]])
    assert pairs == {
        frozenset(("a", "b")),
        frozenset(("a", "c")),
        frozenset(("b", "c")),
    }


def test_same_cluster_pairs_unordered_dedup() -> None:
    # Pair identity is order-free: {a,b} from [a,b] equals {b,a}.
    assert _same_cluster_pairs([["a", "b"]]) == _same_cluster_pairs([["b", "a"]])


def test_identical_clustering_is_perfect() -> None:
    # Case (1): pred == gold, single true pair a-b.
    s = evaluate_er([["a", "b"], ["c"]], [["a", "b"], ["c"]])
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)
    assert s.pair_precision == 1.0
    assert s.pair_recall == 1.0
    assert s.pair_f1 == 1.0


def test_over_merge_creates_false_pairs() -> None:
    # Case (2): [a,b,c] pred vs [a,b],[c] gold.
    #   pred pairs = {a-b, a-c, b-c}; gold pairs = {a-b}
    #   tp=1 (a-b), fp=2 (a-c, b-c), fn=0
    s = evaluate_er([["a", "b", "c"]], [["a", "b"], ["c"]])
    assert (s.tp, s.fp, s.fn) == (1, 2, 0)
    assert s.pair_precision == approx(1 / 3)
    assert s.pair_recall == 1.0


def test_under_merge_misses_expected_pairs() -> None:
    # Case (3): predict all singletons vs [a,b] gold.
    #   pred pairs = {}; gold pairs = {a-b}
    #   tp=0, fp=0, fn=1, recall=0.0
    s = evaluate_er([["a"], ["b"]], [["a", "b"]])
    assert (s.tp, s.fp, s.fn) == (0, 0, 1)
    assert s.pair_recall == 0.0
    # No predicted pairs -> precision defaults to 1.0 (nothing merged wrongly).
    assert s.pair_precision == 1.0
    # p + r != 0 here (p=1, r=0) so f1 = 0.0 by harmonic mean.
    assert s.pair_f1 == 0.0


def test_no_pairs_anywhere_precision_and_recall_one() -> None:
    # Case (4): singletons on both sides -> no pred pairs, no gold pairs.
    s = evaluate_er([["a"], ["b"]], [["a"], ["b"]])
    assert (s.tp, s.fp, s.fn) == (0, 0, 0)
    assert s.pair_precision == 1.0  # no predicted pairs -> 1.0
    assert s.pair_recall == 1.0  # no gold pairs -> 1.0


def test_f1_is_harmonic_mean_on_over_merge() -> None:
    # Case (5): re-check case (2): p=1/3, r=1 -> f1 = 2pr/(p+r) = (2/3)/(4/3) = 1/2.
    s = evaluate_er([["a", "b", "c"]], [["a", "b"], ["c"]])
    p, r = s.pair_precision, s.pair_recall
    harmonic = 2 * p * r / (p + r)
    assert s.pair_f1 == approx(harmonic) == approx(1 / 2)


def test_singleton_only_inputs_all_counts_zero() -> None:
    # Case (6): fully disjoint singletons produce no pairs at all.
    s = evaluate_er([["x"], ["y"], ["z"]], [["x"], ["y"], ["z"]])
    assert (s.tp, s.fp, s.fn) == (0, 0, 0)


def test_as_dict_ints_exact_floats_rounded() -> None:
    # Case (7): precision 1/3 -> 0.3333 rounded; counts pass through as ints.
    s = evaluate_er([["a", "b", "c"]], [["a", "b"], ["c"]])
    d = s.as_dict()
    assert d["tp"] == 1 and d["fp"] == 2 and d["fn"] == 0
    assert isinstance(d["tp"], int)
    assert d["pair_precision"] == round(1 / 3, 4) == 0.3333
    assert d["pair_recall"] == 1.0
    assert d["pair_f1"] == 0.5


def test_erscores_is_frozen() -> None:
    s = evaluate_er([["a", "b"]], [["a", "b"]])
    assert isinstance(s, ERScores)
    try:
        s.tp = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ERScores must be frozen")
