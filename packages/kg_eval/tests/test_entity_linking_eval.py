"""Ranked candidate-list entity-linking metrics: acc@1 / recall@k / MRR / NIL (§23.31/§23.35)."""

from __future__ import annotations

import pytest
from pytest import approx

from kg_eval.entity_linking_eval import (
    LinkingReport,
    _first_rank,
    evaluate,
)


def test_first_rank_is_one_based_and_first_occurrence() -> None:
    # Q1 sits at index 1 (0-based) -> rank 2; a later duplicate is ignored.
    assert _first_rank(["Q2", "Q1", "Q1"], "Q1") == 2
    assert _first_rank(["Q1"], "Q1") == 1
    assert _first_rank(["Q2", "Q3"], "Q1") == 0  # absent -> 0


def test_top1_hit_gives_perfect_acc_and_mrr() -> None:
    # gold Q1, ranked [Q1,Q2]: top-1 == gold -> acc@1 1.0; first rank 1 -> mrr 1.0.
    r = evaluate([{"gold_id": "Q1", "ranked": ["Q1", "Q2"]}])
    assert r.acc_at_1 == 1.0
    assert r.mrr == 1.0
    assert r.recall_at_k == 1.0
    assert r.n == 1 and r.n_nil == 0


def test_gold_at_rank_two_misses_acc_but_recalls() -> None:
    # gold Q1, ranked [Q2,Q1]: top-1 wrong -> acc 0.0; gold in ranked[:5] -> recall 1.0;
    # first rank 2 -> mrr 0.5.
    r = evaluate([{"gold_id": "Q1", "ranked": ["Q2", "Q1"]}])
    assert r.acc_at_1 == 0.0
    assert r.recall_at_k == 1.0
    assert r.mrr == approx(0.5)


def test_recall_at_k_respects_cutoff() -> None:
    # k=1: only ranked[:1] == [Q2] considered, gold Q1 absent -> recall 0.0.
    r = evaluate([{"gold_id": "Q1", "ranked": ["Q2", "Q1"]}], k=1)
    assert r.recall_at_k == 0.0
    assert r.k == 1


def test_nil_record_empty_ranked_is_correct() -> None:
    # gold None + empty ranked: system abstained correctly.
    # nil_accuracy 1.0, and it also counts as an acc@1 hit.
    r = evaluate([{"gold_id": None, "ranked": []}])
    assert r.nil_accuracy == 1.0
    assert r.acc_at_1 == 1.0
    assert r.recall_at_k == 1.0
    assert r.mrr == 1.0
    assert r.n_nil == 1


def test_nil_record_nonempty_ranked_is_wrong() -> None:
    # gold None but system emitted candidates -> NIL wrong; nothing counts as correct.
    r = evaluate([{"gold_id": None, "ranked": ["Q9"]}])
    assert r.nil_accuracy == 0.0
    assert r.acc_at_1 == 0.0
    assert r.recall_at_k == 0.0
    assert r.mrr == 0.0
    assert r.n_nil == 1


def test_two_records_one_hit_one_miss_acc_is_half() -> None:
    # One top-1 hit + one top-1 miss over n=2 -> acc@1 = 1/2.
    r = evaluate(
        [
            {"gold_id": "Q1", "ranked": ["Q1", "Q2"]},  # hit@1
            {"gold_id": "Q1", "ranked": ["Q2", "Q1"]},  # miss@1
        ]
    )
    assert r.acc_at_1 == 0.5
    # recall@5 hits both; mrr = (1 + 1/2) / 2 = 0.75.
    assert r.recall_at_k == 1.0
    assert r.mrr == approx(0.75)


def test_no_nil_records_nil_accuracy_defaults_to_one() -> None:
    # No NIL rows -> empty denominator -> nil_accuracy 1.0 by convention.
    r = evaluate([{"gold_id": "Q1", "ranked": ["Q1"]}])
    assert r.n_nil == 0
    assert r.nil_accuracy == 1.0


def test_empty_records_raises() -> None:
    with pytest.raises(ValueError):
        evaluate([])


def test_bad_k_raises() -> None:
    with pytest.raises(ValueError):
        evaluate([{"gold_id": "Q1", "ranked": ["Q1"]}], k=0)


def test_as_dict_ints_exact_floats_rounded() -> None:
    # mrr for rank-2 gold = 0.5 exact; counts pass through as ints.
    r = evaluate([{"gold_id": "Q1", "ranked": ["Q2", "Q1"]}])
    d = r.as_dict()
    assert d["n"] == 1 and d["n_nil"] == 0 and d["k"] == 5
    assert isinstance(d["n"], int)
    assert d["acc_at_1"] == 0.0
    assert d["recall_at_k"] == 1.0
    assert d["mrr"] == 0.5
    assert d["nil_accuracy"] == 1.0


def test_report_is_frozen() -> None:
    r = evaluate([{"gold_id": "Q1", "ranked": ["Q1"]}])
    assert isinstance(r, LinkingReport)
    try:
        r.n = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("LinkingReport must be frozen")
