"""Tests for char-offset IoU span-set matching (§6.17).

Ручные проверки: значения IoU и матчинга посчитаны вручную из полу-открытых диапазонов.
"""

from __future__ import annotations

from math import isclose

from kg_eval.span_iou_eval import SpanEvalResult, match_spans, span_iou


def test_span_iou_identical() -> None:
    assert span_iou((0, 10), (0, 10)) == 1.0


def test_span_iou_partial_overlap() -> None:
    # inter = 10 - 5 = 5, union = 15 - 0 = 15 -> 5/15
    assert isclose(span_iou((0, 10), (5, 15)), 5 / 15)
    assert isclose(span_iou((0, 10), (5, 15)), 0.3333, abs_tol=1e-4)


def test_span_iou_disjoint() -> None:
    assert span_iou((0, 5), (10, 15)) == 0.0


def test_span_iou_touching_is_zero() -> None:
    # half-open ranges that touch at the boundary do not overlap
    assert span_iou((0, 5), (5, 10)) == 0.0


def test_match_perfect_single() -> None:
    r = match_spans([(0, 10)], [(0, 10)])
    assert r.f1 == 1.0
    assert r.tp == 1
    assert r.fp == 0
    assert r.fn == 0
    assert r.precision == 1.0
    assert r.recall == 1.0


def test_match_two_pred_one_gold_one_to_one() -> None:
    # both preds exceed threshold vs the single gold; greedy picks the best (iou=1.0)
    r = match_spans([(0, 10), (0, 9)], [(0, 10)], 0.5)
    assert r.tp == 1
    assert r.fp == 1
    assert r.fn == 0


def test_match_empty_pred() -> None:
    r = match_spans([], [(0, 5)])
    assert r.recall == 0.0
    assert r.fn == 1
    assert r.tp == 0
    assert r.precision == 0.0


def test_mean_iou_over_matched_pairs() -> None:
    # iou = inter(8) / union(10) = 0.8
    r = match_spans([(0, 10)], [(0, 8)], 0.5)
    assert r.tp == 1
    assert isclose(r.mean_iou, 0.8)


def test_below_threshold_no_match() -> None:
    # iou = 5/15 ~ 0.333 < 0.5 -> no match
    r = match_spans([(0, 10)], [(5, 15)], 0.5)
    assert r.tp == 0
    assert r.fp == 1
    assert r.fn == 1
    assert r.mean_iou == 0.0


def test_as_dict_has_precision() -> None:
    r = match_spans([(0, 10)], [(0, 10)])
    d = r.as_dict()
    assert "precision" in d
    assert set(d) == {"tp", "fp", "fn", "precision", "recall", "f1", "mean_iou"}
    assert isinstance(r, SpanEvalResult)


def test_multi_pair_greedy_assignment() -> None:
    # two golds, two preds; each best pair matched one-to-one
    r = match_spans([(0, 10), (20, 30)], [(0, 9), (21, 30)], 0.5)
    assert r.tp == 2
    assert r.fp == 0
    assert r.fn == 0
    # iou1 = 9/10 = 0.9, iou2 = 9/10 = 0.9
    assert isclose(r.mean_iou, 0.9)
