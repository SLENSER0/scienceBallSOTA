"""Tests for cooling-rate conversion to canonical K/s (§7.2 / §7.8)."""

from __future__ import annotations

import pytest

from kg_common.units.cooling_rate import (
    CoolingRate,
    convert_cooling_rate,
    to_k_per_s,
)


def test_reference_row_60_degc_per_min_is_1_k_per_s() -> None:
    # §7.8 reference table row.
    assert to_k_per_s(60, "degC/min") == pytest.approx(1.0, abs=1e-6)


def test_k_per_s_is_identity() -> None:
    assert to_k_per_s(1, "K/s") == 1.0


def test_convert_k_per_s_to_k_per_min() -> None:
    assert convert_cooling_rate(1, "K/s", "K/min").value == pytest.approx(60, abs=1e-9)


def test_convert_k_per_h_to_k_per_s() -> None:
    assert convert_cooling_rate(3600, "K/h", "K/s").value == pytest.approx(1.0, abs=1e-9)


def test_delta_equivalence_k_and_degc() -> None:
    # A cooling rate is a temperature delta per time; K and degC are equal.
    assert to_k_per_s(5, "K/s") == to_k_per_s(5, "degC/s")


def test_unknown_unit_raises() -> None:
    with pytest.raises(ValueError):
        to_k_per_s(1, "F/min")


def test_unknown_unit_raises_in_convert() -> None:
    with pytest.raises(ValueError):
        convert_cooling_rate(1, "F/min", "K/s")
    with pytest.raises(ValueError):
        convert_cooling_rate(1, "K/s", "F/min")


def test_same_unit_is_direct() -> None:
    assert convert_cooling_rate(2, "degC/min", "degC/min").method == "direct"


def test_cross_unit_is_converted() -> None:
    assert convert_cooling_rate(2, "degC/min", "K/s").method == "converted"


def test_as_dict_k_per_s_matches_magnitude() -> None:
    result = convert_cooling_rate(60, "degC/min", "K/s")
    assert result.as_dict()["k_per_s"] == pytest.approx(1.0, abs=1e-6)


def test_as_dict_full_shape() -> None:
    result = convert_cooling_rate(1, "K/s", "K/min")
    d = result.as_dict()
    assert d == {
        "value": pytest.approx(60, abs=1e-9),
        "unit": "K/min",
        "k_per_s": pytest.approx(1.0, abs=1e-9),
        "method": "converted",
    }


def test_frozen_dataclass_is_immutable() -> None:
    rate = CoolingRate(value=1.0, unit="K/s", k_per_s=1.0, method="direct")
    with pytest.raises((AttributeError, TypeError)):
        rate.value = 2.0  # type: ignore[misc]


def test_degc_per_h_scaling() -> None:
    # 3600 degC/h == 1 K/s.
    assert to_k_per_s(3600, "degC/h") == pytest.approx(1.0, abs=1e-9)
    # Round-trip: 1 K/s back to degC/h == 3600.
    assert convert_cooling_rate(1, "K/s", "degC/h").value == pytest.approx(3600, abs=1e-6)
