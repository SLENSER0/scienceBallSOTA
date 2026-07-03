"""Tests for the canonical §24.13 comparison-criteria registry."""

from __future__ import annotations

import re

import pytest

from kg_retrievers.comparison_criteria import (
    CRITERIA,
    ComparisonCriterion,
    criteria_for_group,
    get_criterion,
    is_benefit,
)

_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")


def test_registry_has_all_canonical_keys() -> None:
    """§24.13 lists ten parameters; each must be registered, incl. 'capex'."""
    assert len(CRITERIA) >= 10
    assert "capex" in CRITERIA
    for key in (
        "efficiency",
        "recovery",
        "removal_efficiency",
        "capex",
        "opex",
        "energy_consumption",
        "cold_climate_applicability",
        "environmental_constraints",
        "maturity_level",
        "domestic_availability",
    ):
        assert key in CRITERIA


def test_benefit_orientation_capex_cost_recovery_benefit() -> None:
    """capex is a cost (lower better); recovery is a benefit (higher better)."""
    assert is_benefit("capex") is False
    assert is_benefit("recovery") is True


def test_energy_consumption_is_cost() -> None:
    """Energy consumption: less is better → benefit False."""
    assert get_criterion("energy_consumption").benefit is False


def test_get_criterion_unknown_raises_keyerror() -> None:
    """An unregistered key must raise KeyError, not return a default."""
    with pytest.raises(KeyError):
        get_criterion("nope")


def test_is_benefit_unknown_raises_keyerror() -> None:
    """is_benefit propagates KeyError for unknown keys."""
    with pytest.raises(KeyError):
        is_benefit("nope")


def test_every_criterion_has_group_and_label() -> None:
    """Every criterion has a non-empty group and non-empty RU label; key matches."""
    for key, crit in CRITERIA.items():
        assert crit.key == key
        assert crit.group != ""
        assert crit.label_ru != ""


def test_all_keys_lowercase_snake_case() -> None:
    """Keys are lowercase snake_case identifiers (shared with MCDA maps)."""
    for key in CRITERIA:
        assert _SNAKE.match(key), key


def test_criteria_for_group_economics_sorted() -> None:
    """economics group is exactly capex, opex — returned sorted by key."""
    econ = criteria_for_group("economics")
    keys = [c.key for c in econ]
    assert keys == sorted(keys)
    assert "capex" in keys
    assert "opex" in keys
    # capex sorts before opex alphabetically.
    assert keys.index("capex") < keys.index("opex")


def test_criteria_for_group_unknown_returns_empty() -> None:
    """A group with no members yields an empty tuple, not an error."""
    assert criteria_for_group("no_such_group") == ()


def test_as_dict_shape_and_benefit_is_bool() -> None:
    """as_dict() carries all five fields; benefit round-trips as a real bool."""
    d = get_criterion("capex").as_dict()
    assert set(d) == {"key", "label_ru", "benefit", "unit", "group"}
    assert isinstance(d["benefit"], bool)
    assert d["benefit"] is False
    assert d["key"] == "capex"
    assert d["group"] == "economics"


def test_criterion_is_frozen() -> None:
    """ComparisonCriterion is immutable (frozen dataclass)."""
    crit = get_criterion("recovery")
    with pytest.raises(AttributeError):
        crit.benefit = False  # type: ignore[misc]


def test_qualitative_criteria_have_no_unit() -> None:
    """Qualitative parameters carry unit=None; numeric ones carry a unit string."""
    assert get_criterion("domestic_availability").unit is None
    assert isinstance(get_criterion("recovery").unit, str)


def test_construct_is_exported() -> None:
    """The dataclass itself is importable for typed callers."""
    crit = ComparisonCriterion("x", "Тест", True, None, "g")
    assert crit.as_dict()["benefit"] is True
