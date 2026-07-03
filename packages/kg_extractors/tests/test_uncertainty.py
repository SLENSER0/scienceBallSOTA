"""§7.9 measurement uncertainty — hand-checked parsing + propagation cases."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.uncertainty import (
    Uncertainty,
    parse_uncertainty,
    propagate_product,
    propagate_sum,
)


def test_abs_form_148_pm_5() -> None:
    u = parse_uncertainty("148 ± 5")
    assert u is not None
    assert u.value == 148.0
    assert u.plus_minus == 5.0
    assert u.lower == 143.0
    assert u.upper == 153.0
    assert u.rel_pct == pytest.approx(5.0 / 148.0 * 100.0)


def test_ascii_plus_minus_148_5() -> None:
    u = parse_uncertainty("148 +/- 5")
    assert u is not None
    assert u.value == 148.0 and u.plus_minus == 5.0
    assert u.lower == 143.0 and u.upper == 153.0


def test_percent_form_148_pm_2pct() -> None:
    # Relative form populates rel_pct AND the derived absolute half-width.
    u = parse_uncertainty("148 ± 2%")
    assert u is not None
    assert u.value == 148.0
    assert u.rel_pct == 2.0
    assert u.plus_minus == pytest.approx(2.96)  # 148 * 0.02
    assert u.lower == pytest.approx(145.04)
    assert u.upper == pytest.approx(150.96)


def test_percent_in_parens_148_3pct() -> None:
    u = parse_uncertainty("148 (±3%)")
    assert u is not None
    assert u.value == 148.0
    assert u.rel_pct == 3.0
    assert u.plus_minus == pytest.approx(4.44)  # 148 * 0.03
    assert u.lower == pytest.approx(143.56)
    assert u.upper == pytest.approx(152.44)


def test_propagate_sum_quadrature_3_4_gives_5() -> None:
    a = parse_uncertainty("10 ± 3")
    b = parse_uncertainty("20 ± 4")
    assert a is not None and b is not None
    s = propagate_sum(a, b)
    assert s.value == 30.0
    assert s.plus_minus == pytest.approx(5.0)  # √(3² + 4²)
    assert s.lower == pytest.approx(25.0)
    assert s.upper == pytest.approx(35.0)


def test_propagate_product_rel_quadrature() -> None:
    # a: 10 ± 0.3 (3 %), b: 20 ± 0.8 (4 %) -> product 200, rel √(3²+4²)=5 %.
    a = parse_uncertainty("10 ± 0.3")
    b = parse_uncertainty("20 ± 0.8")
    assert a is not None and b is not None
    assert a.rel_pct == pytest.approx(3.0)
    assert b.rel_pct == pytest.approx(4.0)
    p = propagate_product(a, b)
    assert p.value == pytest.approx(200.0)
    assert p.rel_pct == pytest.approx(5.0)
    assert p.plus_minus == pytest.approx(10.0)  # 200 * 0.05
    assert p.lower == pytest.approx(190.0)
    assert p.upper == pytest.approx(210.0)


def test_no_uncertainty_returns_none() -> None:
    assert parse_uncertainty("нет данных") is None
    assert parse_uncertainty("abc") is None
    assert parse_uncertainty("") is None
    assert parse_uncertainty("   ") is None


def test_bare_value_is_exact() -> None:
    u = parse_uncertainty("148")
    assert u is not None
    assert u.value == 148.0
    assert u.plus_minus == 0.0
    assert u.rel_pct == 0.0
    assert u.lower == 148.0 and u.upper == 148.0


def test_negative_uncertainty_guard() -> None:
    assert parse_uncertainty("148 ± -5") is None
    assert parse_uncertainty("148 ± -2%") is None


def test_as_dict_has_all_fields() -> None:
    d = parse_uncertainty("148 ± 5").as_dict()  # type: ignore[union-attr]
    assert d == pytest.approx(
        {
            "value": 148.0,
            "plus_minus": 5.0,
            "rel_pct": 5.0 / 148.0 * 100.0,
            "lower": 143.0,
            "upper": 153.0,
        }
    )


def test_frozen_dataclass_is_immutable() -> None:
    u = Uncertainty.from_abs(148.0, 5.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        u.value = 1.0  # type: ignore[misc]
