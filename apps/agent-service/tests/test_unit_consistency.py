"""Tests for §13.16 unit-consistency verifier / тесты проверки единиц."""

from __future__ import annotations

from agent_service.unit_consistency import (
    UnitConflict,
    find_unit_conflicts,
    is_consistent,
)


def test_mixed_hardness_units_one_conflict() -> None:
    """Hardness in HV and MPa -> a single UnitConflict carrying both units."""
    claims = [
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "hardness", "unit": "MPa"},
    ]
    conflicts = find_unit_conflicts(claims)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.quantity == "hardness"
    assert conflict.units == ("HV", "MPa")


def test_all_hv_hardness_no_conflict() -> None:
    """All-HV hardness claims are consistent -> no conflict reported."""
    claims = [
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "hardness", "unit": "HV"},
    ]
    assert find_unit_conflicts(claims) == []


def test_is_consistent_mixed_false_clean_true() -> None:
    """is_consistent is False for the mixed case and True for the clean one."""
    mixed = [
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "hardness", "unit": "MPa"},
    ]
    clean = [
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "hardness", "unit": "HV"},
    ]
    assert is_consistent(mixed) is False
    assert is_consistent(clean) is True


def test_two_self_consistent_quantities_empty() -> None:
    """Two different quantities, each self-consistent -> no conflicts."""
    claims = [
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "hardness", "unit": "HV"},
        {"quantity": "temperature", "unit": "°C"},
        {"quantity": "temperature", "unit": "°C"},
    ]
    assert find_unit_conflicts(claims) == []
    assert is_consistent(claims) is True


def test_empty_claims_empty_and_consistent() -> None:
    """Empty claims list -> no conflicts and is_consistent True."""
    assert find_unit_conflicts([]) == []
    assert is_consistent([]) is True


def test_conflict_units_sorted_and_deduped() -> None:
    """Repeated and out-of-order units collapse to a sorted, de-duplicated tuple."""
    claims = [
        {"quantity": "strength", "unit": "MPa"},
        {"quantity": "strength", "unit": "GPa"},
        {"quantity": "strength", "unit": "MPa"},
        {"quantity": "strength", "unit": "GPa"},
    ]
    conflicts = find_unit_conflicts(claims)
    assert len(conflicts) == 1
    assert conflicts[0].units == ("GPa", "MPa")


def test_as_dict_units_is_list() -> None:
    """UnitConflict.as_dict()['units'] is a plain list, not a tuple."""
    conflict = UnitConflict(quantity="hardness", units=("HV", "MPa"))
    payload = conflict.as_dict()
    assert payload == {"quantity": "hardness", "units": ["HV", "MPa"]}
    assert isinstance(payload["units"], list)
