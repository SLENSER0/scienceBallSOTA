"""Hand-checked tests for typed triple-extraction P/R/F1 (§23.35).

Каждая проверка опирается на вручную посчитанные TP/FP/FN, чтобы micro/macro значения
были воспроизводимы без обращения к реализации.
"""

from __future__ import annotations

from kg_eval.relation_triple_f1 import (
    RelScore,
    TripleF1Report,
    normalize_triple,
    score_triples,
)


def test_normalize_triple_lowercases_and_strips_all_slots() -> None:
    assert normalize_triple(("  Al ", "HAS_PROPERTY", "Ductile")) == (
        "al",
        "has_property",
        "ductile",
    )


def test_identical_gold_and_pred_is_perfect() -> None:
    triples = [("Al", "has_property", "ductile"), ("Fe", "has_property", "magnetic")]
    report = score_triples(triples, triples)
    assert report.micro_f1 == 1.0
    assert report.macro_f1 == 1.0
    assert report.micro_precision == 1.0
    assert report.micro_recall == 1.0


def test_disjoint_sets_are_all_zero() -> None:
    gold = [("Al", "has_property", "ductile")]
    pred = [("Fe", "has_property", "magnetic")]
    report = score_triples(gold, pred)
    assert report.micro_precision == 0.0
    assert report.micro_recall == 0.0
    assert report.micro_f1 == 0.0
    # Единственная релация присутствует и в gold, и в pred: обе стороны дают f1=0.
    assert report.macro_f1 == 0.0


def test_normalization_makes_case_and_space_variants_match() -> None:
    gold = [("Al", "has_property", "ductile")]
    pred = [("al", "HAS_PROPERTY", "Ductile")]
    report = score_triples(gold, pred)
    assert report.micro_f1 == 1.0
    assert report.by_relation[0].tp == 1
    assert report.by_relation[0].fp == 0
    assert report.by_relation[0].fn == 0


def test_one_wrong_object_lowers_recall_and_counts_fn() -> None:
    # gold has ductile; pred says brittle for the same subject/relation.
    gold = [
        ("Al", "has_property", "ductile"),
        ("Fe", "has_property", "magnetic"),
    ]
    pred = [
        ("Al", "has_property", "brittle"),
        ("Fe", "has_property", "magnetic"),
    ]
    report = score_triples(gold, pred)
    rel = report.by_relation[0]
    assert rel.relation == "has_property"
    # TP: (fe,magnetic). FP: (al,brittle). FN: (al,ductile).
    assert rel.tp == 1
    assert rel.fp == 1
    assert rel.fn == 1
    assert rel.recall < 1.0
    assert rel.recall == 0.5
    assert rel.precision == 0.5


def test_duplicate_predicted_triple_collapses_no_double_tp() -> None:
    gold = [("Al", "has_property", "ductile")]
    pred = [
        ("Al", "has_property", "ductile"),
        ("al", "HAS_PROPERTY", "Ductile"),  # normalises to the same triple
    ]
    report = score_triples(gold, pred)
    rel = report.by_relation[0]
    assert rel.tp == 1
    assert rel.fp == 0
    assert rel.fn == 0
    assert report.micro_precision == 1.0


def test_macro_differs_from_micro_when_one_relation_is_rare() -> None:
    # Relation A: 2 gold, both correct -> f1 = 1.0.
    # Relation B: 1 gold, wrong -> f1 = 0.0. Macro = mean(1.0, 0.0) = 0.5.
    gold = [
        ("Al", "has_property", "ductile"),
        ("Fe", "has_property", "magnetic"),
        ("Al", "made_of", "aluminum"),
    ]
    pred = [
        ("Al", "has_property", "ductile"),
        ("Fe", "has_property", "magnetic"),
        ("Al", "made_of", "copper"),  # wrong object
    ]
    report = score_triples(gold, pred)
    assert report.macro_f1 == 0.5
    assert report.micro_f1 != report.macro_f1
    # Micro: TP=2, FP=1, FN=1 -> P=R=F1=2/3.
    assert abs(report.micro_f1 - (2 / 3)) < 1e-9


def test_by_relation_sorted_by_name() -> None:
    gold = [
        ("x", "zeta", "y"),
        ("x", "alpha", "y"),
        ("x", "mu", "y"),
    ]
    report = score_triples(gold, gold)
    names = [r.relation for r in report.by_relation]
    assert names == sorted(names)
    assert names == ["alpha", "mu", "zeta"]


def test_empty_gold_and_empty_pred_is_zero_f1() -> None:
    report = score_triples([], [])
    assert report.micro_f1 == 0.0
    assert report.macro_f1 == 0.0
    assert report.by_relation == ()


def test_report_and_relscore_as_dict_roundtrip() -> None:
    gold = [("Al", "has_property", "ductile")]
    report = score_triples(gold, gold)
    assert isinstance(report, TripleF1Report)
    payload = report.as_dict()
    assert payload["micro_f1"] == 1.0
    assert payload["macro_f1"] == 1.0
    assert isinstance(payload["by_relation"], list)
    rel = report.by_relation[0]
    assert isinstance(rel, RelScore)
    assert rel.as_dict() == {
        "relation": "has_property",
        "tp": 1,
        "fp": 0,
        "fn": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }


def test_frozen_dataclasses_are_immutable() -> None:
    report = score_triples([("a", "r", "b")], [("a", "r", "b")])
    try:
        report.micro_f1 = 0.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("TripleF1Report should be frozen")
