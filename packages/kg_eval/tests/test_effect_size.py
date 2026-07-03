"""Tests for effect-size measures (§23.31).

Hand-checkable assertions on cohens_d + cliffs_delta + analyze. RU/EN.
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.effect_size import (
    EffectSize,
    analyze,
    cliffs_delta,
    cohens_d,
)


def test_identical_distributions_zero_effect() -> None:
    """Одинаковые распределения → d == 0.0, δ == 0.0, magnitude negligible."""
    scores = [0.4, 0.5, 0.6, 0.7]
    res = analyze(scores, scores)
    assert res.cohens_d == 0.0
    assert res.cliffs_delta == 0.0
    assert res.magnitude == "negligible"


def test_shifted_system_positive_cohens_d() -> None:
    """system=[2,3,4] vs baseline=[1,2,3] → сдвиг вверх, d > 0."""
    assert cohens_d([2, 3, 4], [1, 2, 3]) > 0.0


def test_strictly_greater_delta_one_large() -> None:
    """system строго выше на каждой паре → δ == 1.0 и magnitude large."""
    system = [5.0, 6.0, 7.0]
    baseline = [1.0, 2.0, 3.0]
    res = analyze(system, baseline)
    assert res.cliffs_delta == 1.0
    assert res.magnitude == "large"


def test_strictly_less_delta_minus_one() -> None:
    """system строго ниже на каждой паре → δ == -1.0."""
    assert cliffs_delta([1.0, 2.0, 3.0], [5.0, 6.0, 7.0]) == -1.0


def test_cliffs_delta_bounded_in_unit_interval() -> None:
    """δ всегда лежит в [-1, 1] на произвольных данных."""
    system = [0.3, 0.9, 0.1, 0.7, 0.5]
    baseline = [0.2, 0.8, 0.6, 0.4, 0.55]
    d = cliffs_delta(system, baseline)
    assert -1.0 <= d <= 1.0


def test_half_greater_half_less_delta_near_zero() -> None:
    """Половина пар выше, половина ниже симметрично → δ около 0.0."""
    # Every s in {0, 4} beats exactly one b and loses to exactly one b.
    system = [0.0, 4.0]
    baseline = [1.0, 3.0]
    # pairs: 0<1, 0<3, 4>1, 4>3 -> greater 2, less 2 -> delta 0
    d = cliffs_delta(system, baseline)
    assert abs(d) < 1e-9


def test_empty_input_raises() -> None:
    """Пустой system или baseline → ValueError."""
    with pytest.raises(ValueError):
        cohens_d([], [1.0])
    with pytest.raises(ValueError):
        cliffs_delta([1.0], [])
    with pytest.raises(ValueError):
        analyze([], [])


def test_as_dict_has_all_fields() -> None:
    """as_dict() содержит cohens_d, cliffs_delta, magnitude."""
    d = analyze([2.0, 3.0, 4.0], [1.0, 2.0, 3.0]).as_dict()
    assert set(d) == {"cohens_d", "cliffs_delta", "magnitude"}
    assert isinstance(d["magnitude"], str)
    assert d["cohens_d"] > 0.0


def test_effect_size_is_frozen() -> None:
    """EffectSize неизменяем (frozen)."""
    res = analyze([2.0, 3.0], [1.0, 2.0])
    assert isinstance(res, EffectSize)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.cohens_d = 1.0  # type: ignore[misc]


def test_zero_variance_groups_cohens_d_zero() -> None:
    """Нулевая дисперсия в обеих группах → d == 0.0 (нет деления на ноль)."""
    assert cohens_d([3.0, 3.0, 3.0], [3.0, 3.0, 3.0]) == 0.0


def test_magnitude_small_bucket() -> None:
    """δ в диапазоне [0.147, 0.33) → magnitude 'small'."""
    system = [5.0]
    baseline = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    # 5 beats {1,2,3,4}=4 greater, loses to {6,7}=2 less, ties 5; total 7.
    # delta = (4 - 2) / 7 = 0.2857... -> small bucket.
    res = analyze(system, baseline)
    assert res.cliffs_delta == pytest.approx(2 / 7)
    assert res.magnitude == "small"
