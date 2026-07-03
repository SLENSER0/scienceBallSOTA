"""Tests for paired bootstrap significance testing (§23.31).

Hand-checkable assertions on paired_bootstrap + mcnemar. RU/EN.
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.paired_bootstrap import (
    SignificanceResult,
    mcnemar,
    paired_bootstrap,
)


def test_mismatched_lengths_raise() -> None:
    """Разная длина baseline/system → ValueError."""
    with pytest.raises(ValueError):
        paired_bootstrap([0.1, 0.2], [0.3])


def test_empty_input_raises() -> None:
    """Пустой вход → ValueError."""
    with pytest.raises(ValueError):
        paired_bootstrap([], [])


def test_identical_inputs_zero_diff_not_significant() -> None:
    """Одинаковые оценки → mean_diff == 0.0, значимости нет."""
    scores = [0.4, 0.5, 0.6, 0.7]
    res = paired_bootstrap(scores, scores)
    assert res.mean_diff == 0.0
    assert res.significant is False
    assert res.ci_low == 0.0
    assert res.ci_high == 0.0
    assert res.p_value == 1.0


def test_system_strictly_greater_is_significant() -> None:
    """system строго выше на каждом запросе → mean_diff > 0 и p < 0.05."""
    baseline = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    system = [0.30, 0.45, 0.55, 0.62, 0.70, 0.81]
    res = paired_bootstrap(baseline, system)
    assert res.mean_diff > 0.0
    assert res.p_value < 0.05
    assert res.significant is True


def test_determinism_same_seed_same_p() -> None:
    """Один и тот же seed → идентичный p_value (воспроизводимость)."""
    baseline = [0.2, 0.5, 0.1, 0.9, 0.3, 0.4]
    system = [0.4, 0.3, 0.6, 0.5, 0.8, 0.2]
    a = paired_bootstrap(baseline, system, seed=7)
    b = paired_bootstrap(baseline, system, seed=7)
    assert a.p_value == b.p_value
    assert a.ci_low == b.ci_low
    assert a.ci_high == b.ci_high


def test_ci_brackets_mean_diff() -> None:
    """ci_low <= mean_diff <= ci_high всегда выполняется."""
    baseline = [0.1, 0.7, 0.2, 0.6, 0.3, 0.55, 0.44]
    system = [0.3, 0.5, 0.8, 0.4, 0.9, 0.60, 0.20]
    res = paired_bootstrap(baseline, system, seed=3)
    assert res.ci_low <= res.mean_diff <= res.ci_high


def test_mean_diff_sign_matches_direction() -> None:
    """system хуже baseline → mean_diff < 0."""
    baseline = [0.8, 0.9, 0.7, 0.85]
    system = [0.2, 0.3, 0.1, 0.25]
    res = paired_bootstrap(baseline, system)
    assert res.mean_diff < 0.0


def test_as_dict_p_value_in_unit_interval() -> None:
    """as_dict()['p_value'] лежит в [0, 1] и содержит все поля."""
    baseline = [0.1, 0.2, 0.3, 0.4]
    system = [0.2, 0.1, 0.5, 0.3]
    d = paired_bootstrap(baseline, system, seed=1).as_dict()
    assert 0.0 <= d["p_value"] <= 1.0
    assert set(d) == {"n", "mean_diff", "p_value", "ci_low", "ci_high", "significant"}
    assert d["n"] == 4


def test_result_is_frozen() -> None:
    """SignificanceResult неизменяем (frozen)."""
    res = paired_bootstrap([0.1, 0.2], [0.3, 0.4])
    assert isinstance(res, SignificanceResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.p_value = 0.5  # type: ignore[misc]


def test_mcnemar_counts_discordant_pairs() -> None:
    """b = baseline-correct & system-wrong; c = обратное."""
    #            q0     q1     q2     q3     q4
    baseline = [True, True, False, False, True]
    system = [False, True, True, False, False]
    # q0: base right, sys wrong -> b
    # q2: base wrong, sys right -> c
    # q4: base right, sys wrong -> b
    b, c = mcnemar(baseline, system)
    assert b == 2
    assert c == 1


def test_mcnemar_length_mismatch_raises() -> None:
    """Разная длина флагов → ValueError."""
    with pytest.raises(ValueError):
        mcnemar([True, False], [True])
