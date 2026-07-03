"""Тесты фильтров ``GET /experiments`` (§14.8).

Hand-checkable tests for :mod:`api_gateway.experiment_filters`: parsing/validation
of query params and the :func:`matches` predicate.
"""

from __future__ import annotations

import pytest
from api_gateway.experiment_filters import (
    ExperimentFilters,
    matches,
    parse_experiment_filters,
)


def test_min_confidence_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        parse_experiment_filters({"min_confidence": 1.5})
    with pytest.raises(ValueError):
        parse_experiment_filters({"min_confidence": -0.1})


def test_min_confidence_bounds_ok() -> None:
    assert parse_experiment_filters({"min_confidence": 0.0}).min_confidence == 0.0
    assert parse_experiment_filters({"min_confidence": 1.0}).min_confidence == 1.0


def test_material_case_insensitive_match() -> None:
    f = parse_experiment_filters({"material": "al-cu"})
    exp = {"material": "Al-Cu", "confidence": 0.9, "verified": True}
    assert matches(exp, f) is True


def test_material_mismatch() -> None:
    f = parse_experiment_filters({"material": "Ti"})
    assert matches({"material": "Al-Cu"}, f) is False
    # Missing material field on the experiment fails an active material filter.
    assert matches({"confidence": 0.9}, f) is False


def test_operation_case_insensitive() -> None:
    f = parse_experiment_filters({"operation": "ANNEAL"})
    assert matches({"operation": "anneal"}, f) is True
    assert matches({"operation": "quench"}, f) is False


def test_confidence_threshold() -> None:
    f = parse_experiment_filters({"min_confidence": 0.95})
    assert matches({"confidence": 0.9}, f) is False
    assert matches({"confidence": 0.96}, f) is True
    # Non-numeric / absent confidence fails the active threshold.
    assert matches({}, f) is False


def test_verified_only() -> None:
    f = parse_experiment_filters({"verified_only": True})
    assert matches({"verified": False}, f) is False
    assert matches({"verified": True}, f) is True
    assert matches({}, f) is False


def test_verified_only_default_false() -> None:
    assert parse_experiment_filters({}).verified_only is False
    # With verified_only off, unverified experiments still pass.
    assert matches({"verified": False}, parse_experiment_filters({})) is True


def test_date_from_lexicographic() -> None:
    f = parse_experiment_filters({"date_from": "2024-01-01"})
    assert matches({"date": "2023-05-01"}, f) is False
    assert matches({"date": "2024-01-01"}, f) is True
    assert matches({"date": "2024-06-02"}, f) is True
    assert matches({}, f) is False


def test_temperature_and_time_coerced_to_float() -> None:
    f = parse_experiment_filters({"temperature_c": "500", "time_h": "2"})
    assert f.temperature_c == 500.0
    assert isinstance(f.temperature_c, float)
    assert f.time_h == 2.0
    assert isinstance(f.time_h, float)


def test_as_dict_omits_none_and_default_verified_only() -> None:
    d = parse_experiment_filters({"material": "X"}).as_dict()
    assert d == {"material": "X"}
    # §14.8 assertion: exactly one active filter.
    assert len(d) == 1


def test_as_dict_includes_verified_only_when_true() -> None:
    d = parse_experiment_filters({"material": "X", "verified_only": True}).as_dict()
    assert d == {"material": "X", "verified_only": True}


def test_as_dict_full_roundtrip() -> None:
    params = {
        "material": "Al-Cu",
        "operation": "anneal",
        "temperature_c": "500",
        "time_h": "2",
        "atmosphere": "Ar",
        "equipment": "furnace",
        "property": "hardness",
        "regime": "T6",
        "date_from": "2024-01-01",
        "min_confidence": 0.8,
        "verified_only": True,
    }
    d = parse_experiment_filters(params).as_dict()
    assert d["temperature_c"] == 500.0
    assert d["time_h"] == 2.0
    assert d["min_confidence"] == 0.8
    assert d["verified_only"] is True
    assert len(d) == 11


def test_empty_params_all_none() -> None:
    f = parse_experiment_filters({})
    assert f == ExperimentFilters()
    assert f.as_dict() == {}
    assert f.verified_only is False


def test_frozen_immutable() -> None:
    f = parse_experiment_filters({"material": "X"})
    with pytest.raises(AttributeError):
        f.material = "Y"  # type: ignore[misc]
