"""Tests for corrosion-rate canonical target mm/year (§7.2).

Hand-checkable conversions // Проверяемые вручную преобразования:
* 1 mpy = 0.0254 mm/year (1 mil = 0.0254 mm).
* 1 mm/year = 1 / 0.0254 = 39.3701 mpy.
* 1000 um/year = 1.0 mm/year.
* 1 g/(m2*day) on steel (ρ=7.87): 0.365·1/7.87 = 0.04638 mm/year.
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.units.corrosion_rate import (
    CorrosionRate,
    convert_corrosion_rate,
    to_mm_per_year,
)


def test_mpy_to_mm_per_year() -> None:
    assert to_mm_per_year(1, "mpy") == pytest.approx(0.0254, abs=1e-6)


def test_mm_per_year_to_mpy_value() -> None:
    result = convert_corrosion_rate(1, "mm/year", "mpy")
    assert result.value == pytest.approx(39.3701, abs=1e-3)
    assert result.unit == "mpy"
    assert result.method == "converted"


def test_um_per_year_to_mm_per_year() -> None:
    assert to_mm_per_year(1000, "um/year") == pytest.approx(1.0, abs=1e-9)


def test_nm_per_year_to_mm_per_year() -> None:
    assert to_mm_per_year(1_000_000, "nm/year") == pytest.approx(1.0, abs=1e-9)


def test_mass_loss_gmd_with_density() -> None:
    got = to_mm_per_year(1, "g/(m2*day)", density_g_cm3=7.87)
    assert got == pytest.approx(0.04638, abs=1e-4)


def test_mass_loss_gmd_requires_density() -> None:
    with pytest.raises(ValueError):
        to_mm_per_year(1, "g/(m2*day)", density_g_cm3=None)


def test_mass_loss_gmd_rejects_nonpositive_density() -> None:
    with pytest.raises(ValueError):
        to_mm_per_year(1, "g/(m2*day)", density_g_cm3=0.0)


def test_convert_same_unit_is_direct() -> None:
    result = convert_corrosion_rate(0.5, "mm/year", "mm/year")
    assert result.method == "direct"
    assert result.value == pytest.approx(0.5, abs=1e-12)
    assert result.mm_per_year == pytest.approx(0.5, abs=1e-12)


def test_unknown_unit_raises() -> None:
    with pytest.raises(ValueError):
        to_mm_per_year(1, "furlongs/fortnight")


def test_convert_unknown_unit_raises() -> None:
    with pytest.raises(ValueError):
        convert_corrosion_rate(1, "mm/year", "furlongs/fortnight")


def test_as_dict_keys_and_mm_per_year() -> None:
    result = convert_corrosion_rate(2, "mpy", "um/year")
    d = result.as_dict()
    assert set(d.keys()) == {"value", "unit", "mm_per_year", "method"}
    assert d["mm_per_year"] == result.mm_per_year
    # 2 mpy = 0.0508 mm/year = 50.8 um/year.
    assert d["mm_per_year"] == pytest.approx(0.0508, abs=1e-6)
    assert result.value == pytest.approx(50.8, abs=1e-3)


def test_convert_mass_loss_roundtrip() -> None:
    # mm/year -> g/(m2*day) -> mm/year should recover the input.
    to_gmd = convert_corrosion_rate(0.04638, "mm/year", "g/(m2*day)", density_g_cm3=7.87)
    assert to_gmd.value == pytest.approx(1.0, abs=1e-3)
    assert to_gmd.method == "converted"


def test_frozen_dataclass_immutable() -> None:
    result = CorrosionRate(value=1.0, unit="mm/year", mm_per_year=1.0, method="direct")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.value = 2.0  # type: ignore[misc]
