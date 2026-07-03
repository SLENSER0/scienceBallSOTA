"""Gap/contradiction detection metrics (§15.10/§18.6)."""

from __future__ import annotations

from kg_eval.gap_metrics import contradiction_detection_recall, gap_detection_metrics, prf


def test_prf_basic() -> None:
    r = prf({"a", "b", "c"}, {"b", "c", "d"})
    assert r.tp == 2 and r.fp == 1 and r.fn == 1
    assert r.precision == 2 / 3 and r.recall == 2 / 3
    assert abs(r.f1 - 2 / 3) < 1e-9


def test_prf_perfect_and_empty() -> None:
    assert prf({"a"}, {"a"}).f1 == 1.0
    # empty expected + empty predicted → precision/recall 1.0
    r = prf(set(), set())
    assert r.precision == 1.0 and r.recall == 1.0


def test_gap_detection_metrics_by_type_and_subject() -> None:
    predicted = [
        {"gap_type": "missing_unit", "about": "m1"},
        {"gap_type": "orphan_entity", "about": "x9"},  # false positive
    ]
    expected = [
        {"gap_type": "missing_unit", "subject_id": "m1"},  # matched (field-name variant)
        {"gap_type": "missing_equipment", "about": "e2"},  # missed → fn
    ]
    m = gap_detection_metrics(predicted, expected)
    assert m["tp"] == 1 and m["fp"] == 1 and m["fn"] == 1
    assert m["precision"] == 0.5 and m["recall"] == 0.5


def test_contradiction_recall() -> None:
    assert contradiction_detection_recall(["c1"], ["c1", "c2"]) == 0.5
    assert contradiction_detection_recall(["c1", "c2"], ["c1", "c2"]) == 1.0
