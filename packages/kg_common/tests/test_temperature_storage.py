"""Tests for dual temperature storage — тесты §7.2 (degC + kelvin)."""

from __future__ import annotations

import pytest

from kg_common.units.temperature_storage import (
    TemperatureStorage,
    UnknownTemperatureUnitError,
    below_absolute_zero,
    to_storage,
)


def test_degc_180_fills_both_fields() -> None:
    """180 degC → 453.15 K and 180.0 degC — оба поля заполнены."""
    ts = to_storage(180, "degC")
    assert ts.kelvin == 453.15
    assert ts.deg_c == 180.0


def test_degc_100_display_preserved() -> None:
    """100 degC keeps its display value — отображение сохранено."""
    assert to_storage(100, "degC").deg_c == 100.0


def test_degf_212_is_100_degc() -> None:
    """212 degF ≈ 100 degC — точка кипения воды."""
    assert abs(to_storage(212, "degF").deg_c - 100.0) < 1e-6


def test_kelvin_zero_is_absolute_zero_celsius() -> None:
    """0 K → -273.15 degC — абсолютный нуль."""
    assert to_storage(0, "K").deg_c == -273.15


def test_kelvin_300_roundtrips() -> None:
    """300 K stored verbatim in kelvin — кельвин без искажения."""
    assert to_storage(300, "K").kelvin == 300.0


def test_below_absolute_zero_true() -> None:
    """-300 degC is below absolute zero — ниже абсолютного нуля."""
    assert below_absolute_zero(to_storage(-300, "degC")) is True


def test_below_absolute_zero_false() -> None:
    """25 degC is a valid physical temperature — физически возможно."""
    assert below_absolute_zero(to_storage(25, "degC")) is False


def test_celsius_aliases_equivalent() -> None:
    """C and °C behave like degC — синонимы Цельсия."""
    assert to_storage(50, "C").kelvin == to_storage(50, "°C").kelvin == 323.15


def test_kelvin_alias_word() -> None:
    """'kelvin' spelled out matches 'K' — словесная запись."""
    assert to_storage(300, "kelvin").kelvin == 300.0


def test_fahrenheit_aliases_equivalent() -> None:
    """F and °F behave like degF — синонимы Фаренгейта."""
    assert to_storage(32, "F").deg_c == to_storage(32, "°F").deg_c == 0.0


def test_raw_and_unit_carried() -> None:
    """value_raw and from_unit echo the input — сырой ввод сохранён."""
    ts = to_storage(180, "degC")
    assert ts.value_raw == 180
    assert ts.from_unit == "degC"


def test_as_dict_shape() -> None:
    """as_dict exposes all four fields — JSON-готовое отображение."""
    ts = to_storage(0, "K")
    assert ts.as_dict() == {
        "value_raw": 0,
        "from_unit": "K",
        "deg_c": -273.15,
        "kelvin": 0.0,
    }


def test_frozen_dataclass() -> None:
    """TemperatureStorage is immutable — заморожен."""
    ts = to_storage(25, "degC")
    with pytest.raises(AttributeError):
        ts.deg_c = 999.0  # type: ignore[misc]


def test_unknown_unit_raises() -> None:
    """An unsupported unit raises the typed error — неизвестная единица."""
    with pytest.raises(UnknownTemperatureUnitError):
        to_storage(10, "rankine")


def test_type_export() -> None:
    """The exported dataclass is usable directly — прямой импорт типа."""
    ts = TemperatureStorage(value_raw=0.0, from_unit="K", deg_c=-273.15, kelvin=0.0)
    assert below_absolute_zero(ts) is False
