"""Measurement-condition parser tests (§6.6)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.condition_parser import MeasurementCondition, parse_condition


def test_kelvin_converted_to_celsius() -> None:
    # 300 K − 273.15 = 26.85 °C (rounded to 2 dp).
    assert parse_condition("at 300 K").temperature_c == round(26.85, 2)


def test_room_temperature_is_25c() -> None:
    assert parse_condition("at room temperature").temperature_c == 25.0


def test_rt_abbreviation_is_25c() -> None:
    assert parse_condition("RT").temperature_c == 25.0


def test_after_cycles() -> None:
    assert parse_condition("after 1000 cycles").cycles == 1000


def test_n_equals_specimens() -> None:
    assert parse_condition("n=5 specimens").n_samples == 5


def test_specimens_without_n_equals() -> None:
    assert parse_condition("7 specimens tested").n_samples == 7


def test_air_at_celsius() -> None:
    c = parse_condition("in air at 200 °C")
    assert c.temperature_c == 200.0
    assert c.environment == "air"


def test_vacuum_environment() -> None:
    assert parse_condition("tested in vacuum").environment == "vacuum"


def test_inert_collapses_argon() -> None:
    assert parse_condition("under argon atmosphere").environment == "inert"


def test_empty_string_all_none() -> None:
    c = parse_condition("")
    assert c.temperature_c is None
    assert c.cycles is None
    assert c.environment is None
    assert c.n_samples is None
    assert c.raw == ""


def test_as_dict_keys() -> None:
    keys = set(parse_condition("RT").as_dict())
    assert keys == {"temperature_c", "environment", "cycles", "n_samples", "raw"}


def test_cycles_not_read_as_celsius() -> None:
    # «1000 cycles» must NOT be parsed as «1000 C» (leading «c» of «cycles»).
    c = parse_condition("after 1000 cycles")
    assert c.temperature_c is None
    assert c.cycles == 1000


def test_celsius_takes_precedence_over_room() -> None:
    # An explicit °C value wins over any room-temperature prose.
    c = parse_condition("room temperature? no, at 150 °C")
    assert c.temperature_c == 150.0


def test_russian_cues() -> None:
    c = parse_condition("на воздухе при 300 K, 5 образцов, после 500 циклов")
    assert c.environment == "air"
    assert c.temperature_c == round(300 - 273.15, 2)
    assert c.n_samples == 5
    assert c.cycles == 500


def test_negative_celsius() -> None:
    assert parse_condition("at -40 °C").temperature_c == -40.0


def test_dataclass_is_frozen() -> None:
    c = parse_condition("RT")
    with pytest.raises(FrozenInstanceError):
        c.temperature_c = 0.0  # type: ignore[misc]


def test_construct_directly() -> None:
    c = MeasurementCondition(
        temperature_c=25.0, environment="air", cycles=None, n_samples=None, raw="x"
    )
    assert c.as_dict()["environment"] == "air"
