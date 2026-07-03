"""Tests for ASTM E112 grain-size conversions (§7.2).

Hand-checkable against the published ASTM E112 grain-size table.
Ручная проверка по таблице ASTM E112.
"""

from __future__ import annotations

import math

import pytest

from kg_common.units.grain_size import (
    GrainSize,
    astm_g_to_diameter_um,
    diameter_um_to_astm_g,
    grain_size_from_g,
)


def test_diameter_matches_astm_table() -> None:
    # Reference diameters from the ASTM E112 grain-size table.
    assert astm_g_to_diameter_um(1) == pytest.approx(254, abs=2)
    assert astm_g_to_diameter_um(5) == pytest.approx(63.5, abs=1)
    assert astm_g_to_diameter_um(8) == pytest.approx(22.5, abs=1)


def test_round_trip_g_to_diameter_to_g() -> None:
    assert diameter_um_to_astm_g(astm_g_to_diameter_um(6)) == pytest.approx(6.0, abs=1e-6)


def test_inverse_from_reference_diameter() -> None:
    assert diameter_um_to_astm_g(254) == pytest.approx(1.0, abs=0.02)


def test_grains_per_mm2_value() -> None:
    # G=7 → N_A = 2**6 * 15.500 = 992 grains/mm².
    assert grain_size_from_g(7).grains_per_mm2 == pytest.approx(992, rel=1e-3)


def test_grain_size_as_dict() -> None:
    d = grain_size_from_g(3).as_dict()
    assert d["astm_g"] == 3
    assert set(d) == {"astm_g", "diameter_um", "grains_per_mm2"}


def test_finer_g_means_smaller_diameter() -> None:
    # Larger grain number ⇒ finer structure ⇒ smaller mean diameter.
    assert astm_g_to_diameter_um(1) > astm_g_to_diameter_um(10)


def test_grain_size_record_fields() -> None:
    gs = grain_size_from_g(5)
    assert isinstance(gs, GrainSize)
    assert gs.astm_g == 5
    assert gs.diameter_um == pytest.approx(63.5, abs=1)
    assert gs.grains_per_mm2 == pytest.approx(2.0**4 * 15.5, rel=1e-9)


def test_diameter_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        diameter_um_to_astm_g(0.0)


def test_diameter_um_matches_direct_formula() -> None:
    # Cross-check forward formula against N_A = 2**(G-1)*15.5, d=sqrt(1/N_A).
    for g in (2, 4, 6, 9):
        n_a = 2.0 ** (g - 1) * 15.5
        assert astm_g_to_diameter_um(g) == pytest.approx(math.sqrt(1 / n_a) * 1000, rel=1e-9)
