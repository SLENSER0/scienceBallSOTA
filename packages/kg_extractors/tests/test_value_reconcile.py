"""Tests for cross-layer numeric reconciliation (§6.13).

Тесты согласования числовых значений между слоями извлечения.
"""

from __future__ import annotations

import pytest

from kg_extractors.value_reconcile import Reconciled, reconcile_numeric


def test_agreeing_layers_no_conflict() -> None:
    # 148 vs 149: |149-148|/149 = 0.0067 < 0.02 => agree (§6.13).
    r = reconcile_numeric([("rule", 148.0, "HV"), ("llm", 149.0, "HV")])
    assert r.conflict is False


def test_agreeing_layers_rule_wins() -> None:
    # rule outranks llm: rule fact preferred for numbers (§6.13).
    r = reconcile_numeric([("rule", 148.0, "HV"), ("llm", 149.0, "HV")])
    assert r.chosen_layer == "rule"


def test_diverging_values_flag_conflict() -> None:
    # 148 vs 180: |180-148|/180 = 0.178 > 0.02 => conflict, needs review.
    r = reconcile_numeric([("rule", 148.0, "HV"), ("llm", 180.0, "HV")])
    assert r.conflict is True


def test_spread_is_max_minus_min() -> None:
    r = reconcile_numeric([("rule", 148.0, "HV"), ("llm", 180.0, "HV")])
    assert r.spread == 32.0


def test_single_candidate_never_conflicts() -> None:
    r = reconcile_numeric([("llm", 150.0, "HV")])
    assert r.conflict is False


def test_single_candidate_zero_spread() -> None:
    r = reconcile_numeric([("llm", 150.0, "HV")])
    assert r.spread == 0.0


def test_priority_llm_beats_ml() -> None:
    # llm precedes ml in default priority => llm wins even when equal values.
    r = reconcile_numeric([("ml", 100.0, None), ("llm", 100.0, None)])
    assert r.chosen_layer == "llm"


def test_conflict_winner_still_highest_priority() -> None:
    # Winner is priority-driven regardless of who reported the larger number.
    r = reconcile_numeric([("llm", 180.0, "HV"), ("rule", 148.0, "HV")])
    assert r.chosen_layer == "rule"
    assert r.value == 148.0
    assert r.unit == "HV"


def test_as_dict_keys() -> None:
    keys = set(reconcile_numeric([("rule", 1.0, None)]).as_dict())
    assert keys == {"value", "unit", "chosen_layer", "conflict", "spread"}


def test_as_dict_values_roundtrip() -> None:
    r = reconcile_numeric([("rule", 148.0, "HV"), ("llm", 180.0, "HV")])
    assert r.as_dict() == {
        "value": 148.0,
        "unit": "HV",
        "chosen_layer": "rule",
        "conflict": True,
        "spread": 32.0,
    }


def test_frozen_dataclass_immutable() -> None:
    r = reconcile_numeric([("rule", 1.0, None)])
    assert isinstance(r, Reconciled)
    with pytest.raises(AttributeError):
        r.value = 2.0  # type: ignore[misc]


def test_custom_priority_overrides_default() -> None:
    # Caller can prefer ml over rule via explicit layer_priority.
    r = reconcile_numeric(
        [("rule", 10.0, None), ("ml", 10.1, None)],
        layer_priority=("ml", "rule", "llm"),
    )
    assert r.chosen_layer == "ml"


def test_unknown_layer_ranks_last() -> None:
    # A layer absent from priority loses to any known layer.
    r = reconcile_numeric([("mystery", 5.0, None), ("llm", 5.0, None)])
    assert r.chosen_layer == "llm"


def test_empty_candidates_raises() -> None:
    with pytest.raises(ValueError):
        reconcile_numeric([])
