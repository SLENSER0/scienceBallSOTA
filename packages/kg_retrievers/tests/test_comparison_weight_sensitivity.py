"""Tests for weight-sensitivity of an MCDA ranking (§24.13).

Проверяем: доминирующая альтернатива робастна; почти-ничья хрупка; базовые
свойства ``weighted_totals`` и сериализации. Все числа проверяемы вручную.
"""

from __future__ import annotations

import pytest

from kg_retrievers.comparison_weight_sensitivity import (
    SensitivityResult,
    analyze_sensitivity,
    weighted_totals,
)


def test_dominant_alternative_is_robust() -> None:
    """(1) Alt best on every criterion → robust True, min_flip_delta None."""
    matrix = {
        "A": {"c1": 0.90, "c2": 0.80, "c3": 1.00},
        "B": {"c1": 0.20, "c2": 0.10, "c3": 0.30},
        "C": {"c1": 0.05, "c2": 0.40, "c3": 0.15},
    }
    weights = {"c1": 1.0, "c2": 1.0, "c3": 1.0}
    result = analyze_sensitivity(matrix, weights)
    assert result.top_id == "A"
    assert result.robust is True
    assert result.min_flip_delta is None
    assert result.flipping_criterion is None


def test_near_tied_alternatives_flip() -> None:
    """(2)+(4)+(7) Near-tied pair → robust False, valid flipping_criterion, delta>0.

    Baseline (equal weights 0.5/0.5): A = 0.55, B = 0.54 → A leads by 0.01. Adding
    ``delta`` to c2 (renormalizing c1 to ``0.5 - delta``) gives A = 0.55 - 0.10*delta
    and B = 0.54 + 0.08*delta; B overtakes A once delta > 0.0556, i.e. at the second
    step (delta = 0.10) with step 0.05. Boosting c1 (A's stronger column) never flips.
    """
    matrix = {
        "A": {"c1": 0.60, "c2": 0.50},
        "B": {"c1": 0.50, "c2": 0.58},
    }
    weights = {"c1": 0.5, "c2": 0.5}
    result = analyze_sensitivity(matrix, weights, step=0.05)
    assert result.top_id == "A"
    assert result.robust is False
    assert result.flipping_criterion == "c2"
    assert result.min_flip_delta == pytest.approx(0.10)
    assert result.min_flip_delta > 0.0
    assert result.flipping_criterion in matrix["A"]


def test_weighted_totals_single_criterion_equals_column() -> None:
    """(3) A single-criterion matrix weighted at 1.0 returns that column verbatim."""
    matrix = {"A": {"c1": 0.70}, "B": {"c1": 0.30}, "C": {"c1": 0.55}}
    weights = {"c1": 1.0}
    totals = weighted_totals(matrix, weights)
    assert totals == pytest.approx({"A": 0.70, "B": 0.30, "C": 0.55})


def test_weighted_totals_multi_criterion() -> None:
    """weighted_totals is the raw sum(value * weight), no weight renormalization."""
    matrix = {"A": {"c1": 0.5, "c2": 0.2}, "B": {"c1": 0.1, "c2": 0.9}}
    totals = weighted_totals(matrix, {"c1": 2.0, "c2": 1.0})
    assert totals["A"] == pytest.approx(0.5 * 2.0 + 0.2 * 1.0)
    assert totals["B"] == pytest.approx(0.1 * 2.0 + 0.9 * 1.0)


def test_empty_matrix_raises() -> None:
    """(5) Empty matrix → ValueError from both entry points."""
    with pytest.raises(ValueError):
        analyze_sensitivity({}, {"c1": 1.0})
    with pytest.raises(ValueError):
        weighted_totals({}, {"c1": 1.0})


def test_as_dict_robust_is_bool_and_criterion_valid() -> None:
    """(6)+(7) as_dict()['robust'] is a bool; flipping_criterion is a key or None."""
    matrix = {"A": {"c1": 0.9, "c2": 0.9}, "B": {"c1": 0.1, "c2": 0.1}}
    result = analyze_sensitivity(matrix, {"c1": 1.0, "c2": 1.0})
    payload = result.as_dict()
    assert isinstance(payload["robust"], bool)
    assert payload["robust"] is True
    assert result.flipping_criterion is None or result.flipping_criterion in matrix["A"]
    assert isinstance(result, SensitivityResult)


def test_bad_step_and_zero_weights_raise() -> None:
    """Non-positive step or degenerate (zero-sum) weights are rejected."""
    matrix = {"A": {"c1": 0.6}, "B": {"c1": 0.4}}
    with pytest.raises(ValueError):
        analyze_sensitivity(matrix, {"c1": 1.0}, step=0.0)
    with pytest.raises(ValueError):
        analyze_sensitivity(matrix, {"c1": 0.0}, step=0.05)
