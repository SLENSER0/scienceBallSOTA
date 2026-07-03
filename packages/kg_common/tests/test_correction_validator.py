"""Tests for action ``correct`` unit validation / normalization (§16.6).

Hand-checkable arithmetic against the SI-prefix expander and the conversion
registry: ``1 km == 1000 m``, ``100 cm == 1 m``, mass ↔ length is rejected.
"""

from __future__ import annotations

from kg_common.storage.correction_validator import (
    STATUS_DIMENSION_MISMATCH,
    STATUS_OK,
    CorrectionResult,
    raise_status,
    validate_correction,
)


def test_km_to_m_normalizes_to_1000() -> None:
    result = validate_correction(1.0, "km", "m")
    assert result.ok is True
    assert result.value_normalized == 1000.0
    assert result.base_unit == "m"


def test_cm_to_m_normalizes_to_one() -> None:
    result = validate_correction(100, "cm", "m")
    assert result.ok is True
    assert result.value_normalized == 1.0
    assert result.base_unit == "m"


def test_dimension_mismatch_mass_vs_length() -> None:
    result = validate_correction(5, "kg", "m")
    assert result.ok is False
    assert result.error is not None
    assert result.value_normalized is None
    assert result.base_unit is None


def test_raise_status_mismatch_is_422() -> None:
    result = validate_correction(5, "kg", "m")
    assert raise_status(result) == 422
    assert STATUS_DIMENSION_MISMATCH == 422


def test_raise_status_ok_is_200() -> None:
    assert raise_status(validate_correction(2, "m", "m")) == 200
    assert STATUS_OK == 200


def test_same_unit_returns_input_value() -> None:
    result = validate_correction(2.0, "m", "m")
    assert result.ok is True
    assert result.value_normalized == 2.0


def test_same_unit_non_integer_value_preserved() -> None:
    result = validate_correction(3.25, "m", "m")
    assert result.value_normalized == 3.25


def test_as_dict_echoes_new_unit() -> None:
    result = validate_correction(1.0, "km", "m")
    payload = result.as_dict()
    assert payload["unit"] == "km"
    assert payload["value"] == 1.0
    assert payload["value_normalized"] == 1000.0
    assert payload["base_unit"] == "m"
    assert payload["ok"] is True
    assert payload["error"] is None


def test_as_dict_on_failure_echoes_unit_and_nulls() -> None:
    result = validate_correction(5, "kg", "m")
    payload = result.as_dict()
    assert payload["unit"] == "kg"
    assert payload["value_normalized"] is None
    assert payload["base_unit"] is None
    assert payload["error"] is not None


def test_result_is_frozen() -> None:
    result = validate_correction(1.0, "km", "m")
    import dataclasses

    try:
        result.ok = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("CorrectionResult must be frozen")


def test_unknown_target_unit_rejected() -> None:
    result = validate_correction(1.0, "m", "banana")
    assert result.ok is False
    assert result.value_normalized is None
    assert raise_status(result) == 422


def test_construct_result_directly() -> None:
    result = CorrectionResult(
        ok=True,
        value=1.0,
        unit="km",
        value_normalized=1000.0,
        base_unit="m",
        error=None,
    )
    assert result.as_dict()["unit"] == "km"
