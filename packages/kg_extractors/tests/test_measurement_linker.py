"""Measurement linker → MeasurementExtract (§6.6).

Hand-checked cases: value/unit/baseline association, effect-direction cues
(RU/EN), method vocabulary, unit↔property mismatch, nearest-value selection,
and the ``as_dict`` round-trip.
"""

from __future__ import annotations

from kg_extractors.measurement_linker import MeasurementExtract, link_measurements
from kg_extractors.property_extractor import PropertyMention


def _hardness(text: str) -> PropertyMention:
    """Build a hardness mention for the literal 'hardness'/'твёрдость' in *text*."""
    for surface in ("hardness", "твёрдость", "твердость"):
        i = text.lower().find(surface)
        if i >= 0:
            span = (i, i + len(surface))
            return PropertyMention("prop:hardness", text[i : i + len(surface)], span)
    raise AssertionError("no hardness surface in text")


def test_hardness_increase_with_baseline() -> None:
    text = "hardness increased to 148 HV (from 90 HV)"
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.property_id == "prop:hardness"
    assert m.value == 148
    assert m.unit == "HV"
    assert m.baseline_value == 90
    assert m.effect_direction == "increase"
    assert m.unit_property_mismatch is False
    assert "148 HV" in m.source_span


def test_method_vickers() -> None:
    text = "Hardness was measured by Vickers indenter at 148 HV."
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.method == "Vickers"
    assert m.value == 148


def test_method_xrd() -> None:
    text = "Phases were identified by XRD; hardness reached 148 HV."
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.method == "XRD"


def test_method_hrtem_wins_over_tem() -> None:
    text = "Grains imaged by HRTEM; hardness was 148 HV."
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.method == "HRTEM"


def test_effect_decrease_ru() -> None:
    text = "твёрдость снизилась до 90 HV"
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.effect_direction == "decrease"
    assert m.value == 90
    assert m.unit == "HV"
    assert m.baseline_value is None


def test_no_change_neutral() -> None:
    text = "hardness showed no change at 120 HV"
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.effect_direction == "no_change"
    assert m.value == 120


def test_direction_none_without_cue() -> None:
    text = "the measured hardness was 148 HV"
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.effect_direction is None


def test_unit_property_mismatch_flagged() -> None:
    # МПа is not an allowed unit for hardness (HV / HB / HRC).
    text = "The hardness was reported as 500 MPa."
    (m,) = link_measurements(text, [_hardness(text)])
    assert m.unit == "MPa"
    assert m.value == 500
    assert m.unit_property_mismatch is True


def test_nearest_value_with_two_numbers() -> None:
    text = "Sample hardness was 148 HV; the temperature was 300 C."
    (m,) = link_measurements(text, [_hardness(text)])
    # 148 is adjacent to 'hardness'; 300 is far away — nearest must win.
    assert m.value == 148
    assert m.unit == "HV"


def test_as_dict_round_trip() -> None:
    text = "hardness increased to 148 HV (from 90 HV)"
    (m,) = link_measurements(text, [_hardness(text)])
    d = m.as_dict()
    assert isinstance(m, MeasurementExtract)
    assert d == {
        "property_id": "prop:hardness",
        "value": 148,
        "unit": "HV",
        "baseline_value": 90,
        "effect_direction": "increase",
        "method": None,
        "source_span": d["source_span"],
        "unit_property_mismatch": False,
    }
    assert set(d) == {
        "property_id",
        "value",
        "unit",
        "baseline_value",
        "effect_direction",
        "method",
        "source_span",
        "unit_property_mismatch",
    }


def test_empty_inputs() -> None:
    assert link_measurements("", [_hardness("hardness 1 HV")]) == []
    assert link_measurements("hardness 148 HV", []) == []
