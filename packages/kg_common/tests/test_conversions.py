"""Extended unit-conversion registry (§7.10).

Hand-checked conversions with concrete expected values across every dimension
family, plus the dimension / compatibility helpers and the cross-dimension
:class:`IncompatibleUnitsError` guard.
"""

from __future__ import annotations

import pytest

from kg_common.units.conversions import (
    BASE_UNITS,
    CONVERSIONS,
    DIMENSIONS,
    IncompatibleUnitsError,
    UnknownUnitError,
    are_compatible,
    convert,
    dimension_of,
)


def test_celsius_to_kelvin_exact() -> None:
    # 100 °C = 100 + 273.15 K, by definition.
    assert convert(100, "°C", "K") == 373.15
    assert convert(0, "°C", "K") == 273.15


def test_mpa_to_bar_exact() -> None:
    # 1 MPa = 10 bar (1 bar = 100 kPa, 1 MPa = 1000 kPa).
    assert convert(1, "MPa", "bar") == 10.0


def test_atm_to_kpa_standard() -> None:
    # Standard atmosphere: 1 atm = 101.325 kPa exactly.
    assert convert(1, "atm", "kPa") == pytest.approx(101.325)


def test_kcal_to_joule_thermochemical() -> None:
    # Thermochemical calorie: 1 cal = 4.184 J ⇒ 1 kcal = 4184 J.
    assert convert(1, "kcal", "J") == 4184.0
    assert convert(1, "cal", "J") == pytest.approx(4.184)


def test_percent_to_ppm_exact() -> None:
    # 1 % = 10 000 ppm; 1 fraction = 100 %.
    assert convert(1, "%", "ppm") == 10000.0
    assert convert(1, "fraction", "%") == 100.0


def test_micrometre_to_nanometre_x1000() -> None:
    # 1 µm = 1000 nm; ASCII alias "um" and 1 m = 1000 mm as well.
    assert convert(1, "µm", "nm") == 1000.0
    assert convert(1, "um", "nm") == 1000.0
    assert convert(1, "m", "mm") == 1000.0


def test_fahrenheit_anchor_points() -> None:
    # Water freezes at 32 °F = 0 °C and boils at 212 °F = 100 °C.
    assert convert(32, "°F", "°C") == pytest.approx(0.0, abs=1e-9)
    assert convert(212, "°F", "°C") == pytest.approx(100.0)
    assert convert(0, "°C", "°F") == pytest.approx(32.0)


def test_ev_to_joule_codata() -> None:
    # CODATA elementary charge in joules per electronvolt.
    assert convert(1, "eV", "J") == pytest.approx(1.602176634e-19)


def test_incompatible_dimensions_raise() -> None:
    # Temperature ↔ pressure is physically meaningless — must raise.
    with pytest.raises(IncompatibleUnitsError):
        convert(100, "°C", "MPa")
    with pytest.raises(IncompatibleUnitsError):
        convert(1, "J", "nm")
    # IncompatibleUnitsError is a ValueError so callers may catch it broadly.
    assert issubclass(IncompatibleUnitsError, ValueError)


def test_unknown_unit_raises() -> None:
    with pytest.raises(UnknownUnitError):
        convert(1, "furlong", "m")
    with pytest.raises(UnknownUnitError):
        dimension_of("furlong")


def test_dimension_of() -> None:
    assert dimension_of("°F") == "temperature"
    assert dimension_of("psi") == "pressure"
    assert dimension_of("kcal") == "energy"
    assert dimension_of("nm") == "length"
    assert dimension_of("ppm") == "fraction"


def test_are_compatible() -> None:
    assert are_compatible("MPa", "psi") is True
    assert are_compatible("°C", "K") is True
    assert are_compatible("°C", "MPa") is False
    # Never raises on an unknown unit — just False.
    assert are_compatible("banana", "MPa") is False


def test_round_trip_is_stable() -> None:
    # Convert out and back; affine and linear conversions both round-trip.
    assert convert(convert(50, "°C", "°F"), "°F", "°C") == pytest.approx(50.0)
    assert convert(convert(7.5, "MPa", "psi"), "psi", "MPa") == pytest.approx(7.5)
    assert convert(convert(42, "µm", "nm"), "nm", "µm") == pytest.approx(42.0)


def test_registry_shape() -> None:
    # Every dimension has a base unit whose spec is identity (scale 1, offset 0).
    assert set(BASE_UNITS) == set(DIMENSIONS)
    for dim, base in BASE_UNITS.items():
        spec = CONVERSIONS[base]
        assert spec.dimension == dim
        assert spec.scale == 1.0 and spec.offset == 0.0
    # as_dict() exposes the four spec fields.
    assert CONVERSIONS["MPa"].as_dict() == {
        "symbol": "MPa",
        "dimension": "pressure",
        "scale": 1000.0,
        "offset": 0.0,
    }
