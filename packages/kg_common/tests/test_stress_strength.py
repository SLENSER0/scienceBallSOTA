"""Tests for the §7.2 stress/strength → MPa converter — тесты (§7.2).

Hand-checkable conversions to the canonical target unit ``MPa`` covering every
accepted input unit (GPa, kPa, Pa, ksi, psi, N/mm2, kgf/mm2), the
:class:`StressConversion` record and the unknown-unit guard.
"""

from __future__ import annotations

import pytest

from kg_common.units.stress_strength import (
    StressConversion,
    UnknownStressUnitError,
    convert_stress,
    to_mpa,
)


def test_mpa_identity() -> None:
    assert to_mpa(320.0, "MPa") == 320.0


def test_gpa_is_1000_mpa() -> None:
    # 1 ГПа = 1000 МПа (exact).
    assert to_mpa(1, "GPa") == 1000.0
    assert to_mpa(0.207, "GPa") == 207.0


def test_kpa_and_pa_scale_down() -> None:
    # 1000 кПа = 1 МПа; 1e6 Па = 1 МПа.
    assert to_mpa(1000, "kPa") == 1.0
    assert to_mpa(1_000_000, "Pa") == pytest.approx(1.0)


def test_ksi_constant() -> None:
    # 1 ksi = 6.894757 МПа (datasheet constant).
    assert abs(to_mpa(1, "ksi") - 6.894757) < 1e-6


def test_ksi_datasheet_value() -> None:
    # 46.5 ksi ≈ 320.606 МПа — a typical yield-strength row.
    assert abs(to_mpa(46.5, "ksi") - 320.606) < 0.1


def test_psi_is_milli_ksi() -> None:
    assert abs(to_mpa(1, "psi") - 6.894757e-3) < 1e-9
    # 1000 psi == 1 ksi.
    assert to_mpa(1000, "psi") == pytest.approx(to_mpa(1, "ksi"))


def test_n_per_mm2_is_exact_mpa() -> None:
    # 1 Н/мм² ≡ 1 МПа (exact synonym), including spelling aliases.
    assert to_mpa(1, "N/mm2") == 1.0
    assert to_mpa(250, "N/mm^2") == 250.0
    assert to_mpa(250, "N/mm²") == 250.0


def test_kgf_per_mm2_constant() -> None:
    # 1 кгс/мм² = 9.80665 МПа (g0, exact).
    assert abs(to_mpa(1, "kgf/mm2") - 9.80665) < 1e-6
    assert abs(to_mpa(20, "kgf/mm2") - 196.133) < 1e-3


def test_whitespace_tolerated() -> None:
    assert to_mpa(1, "  GPa ") == 1000.0


def test_convert_stress_record() -> None:
    conv = convert_stress(2, "GPa", "MPa")
    assert isinstance(conv, StressConversion)
    assert conv.value_raw == 2
    assert conv.from_unit == "GPa"
    assert conv.value_mpa == 2000.0
    assert conv.target == "MPa"


def test_convert_stress_default_target_is_mpa() -> None:
    conv = convert_stress(46.5, "ksi", "MPa")
    assert conv.target == "MPa"
    assert abs(conv.value_mpa - 320.606) < 0.1


def test_stress_conversion_frozen() -> None:
    conv = convert_stress(1, "MPa", "MPa")
    with pytest.raises((AttributeError, TypeError)):
        conv.value_mpa = 5.0  # type: ignore[misc]


def test_as_dict_round_trip() -> None:
    conv = convert_stress(1, "GPa", "MPa")
    d = conv.as_dict()
    assert d == {
        "value_raw": 1,
        "from_unit": "GPa",
        "value_mpa": 1000.0,
        "target": "MPa",
    }


def test_default_target_field() -> None:
    # StressConversion.target defaults to the canonical MPa.
    conv = StressConversion(value_raw=1.0, from_unit="MPa", value_mpa=1.0)
    assert conv.target == "MPa"


def test_unknown_unit_raises() -> None:
    # HV is a hardness scale, not a stress unit — должно падать.
    with pytest.raises(UnknownStressUnitError):
        to_mpa(320, "HV")
    with pytest.raises(UnknownStressUnitError):
        convert_stress(1, "HV", "MPa")


def test_unknown_target_raises() -> None:
    with pytest.raises(UnknownStressUnitError):
        convert_stress(1, "MPa", "HV")
