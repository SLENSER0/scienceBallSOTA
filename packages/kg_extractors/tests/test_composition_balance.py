"""Tests for composition balance resolution + sum validation (§6.21)."""

from __future__ import annotations

from kg_extractors.composition_balance import (
    Fraction,
    balance_composition,
    validate_sums,
)


def test_balance_resolved() -> None:
    # Fe balance in Fe-18Cr-8Ni: 100 - (18 + 8) = 74.
    fractions = [
        {"element": "Fe", "value": None, "is_balance": True},
        {"element": "Cr", "value": 18.0},
        {"element": "Ni", "value": 8.0},
    ]
    out = balance_composition(fractions)
    by_el = {f.element: f.value for f in out}
    assert by_el == {"Fe": 74.0, "Cr": 18.0, "Ni": 8.0}
    # Order preserved.
    assert [f.element for f in out] == ["Fe", "Cr", "Ni"]


def test_resolved_sums_to_100() -> None:
    fractions = [
        {"element": "Cu", "value": None, "is_balance": True},
        {"element": "Zn", "value": 30.0},
        {"element": "Pb", "value": 2.5},
    ]
    balanced = balance_composition(fractions)
    report = validate_sums(balanced)
    assert report == {"ok": True, "total": 100.0, "residual": 0.0}


def test_over_100_flagged() -> None:
    # Fixed elements already exceed 100 -> residual negative, not ok.
    fractions = [
        {"element": "Cr", "value": 60.0},
        {"element": "Ni", "value": 45.0},
    ]
    report = validate_sums(fractions)
    assert report["ok"] is False
    assert report["total"] == 105.0
    assert report["residual"] == -5.0


def test_no_balance_passes_through() -> None:
    fractions = [
        {"element": "Al", "value": 96.0},
        {"element": "Cu", "value": 4.0},
    ]
    out = balance_composition(fractions)
    assert [(f.element, f.value) for f in out] == [("Al", 96.0), ("Cu", 4.0)]
    assert validate_sums(out)["ok"] is True


def test_multiple_balance_elements_split_evenly() -> None:
    # Residual = 100 - 20 = 80, split across two balance elements -> 40 each.
    fractions = [
        {"element": "Cr", "value": 20.0},
        {"element": "Fe", "value": None, "is_balance": True},
        {"element": "Ni", "value": None, "is_balance": True},
    ]
    out = balance_composition(fractions)
    by_el = {f.element: f.value for f in out}
    assert by_el == {"Cr": 20.0, "Fe": 40.0, "Ni": 40.0}
    assert validate_sums(out) == {"ok": True, "total": 100.0, "residual": 0.0}


def test_empty() -> None:
    assert balance_composition([]) == []
    report = validate_sums([])
    assert report == {"ok": False, "total": 0.0, "residual": 100.0}


def test_as_dict_roundtrip() -> None:
    frac = Fraction(element="Fe", value=74.0, is_balance=True)
    assert frac.as_dict() == {"element": "Fe", "value": 74.0, "is_balance": True}
    # Default is_balance is False.
    assert Fraction("Cr", 18.0).as_dict() == {
        "element": "Cr",
        "value": 18.0,
        "is_balance": False,
    }


def test_accepts_fraction_objects() -> None:
    fractions = [
        Fraction("Fe", None, is_balance=True),
        Fraction("C", 0.8),
    ]
    out = balance_composition(fractions)
    by_el = {f.element: f.value for f in out}
    assert by_el == {"Fe": 99.2, "C": 0.8}


def test_custom_total() -> None:
    # Atomic fraction target of 1.0 instead of 100.
    fractions = [
        {"element": "Ti", "value": None, "is_balance": True},
        {"element": "Al", "value": 0.4},
    ]
    out = balance_composition(fractions, total=1.0)
    by_el = {f.element: round(f.value, 6) for f in out}
    assert by_el == {"Ti": 0.6, "Al": 0.4}
    assert validate_sums(out, total=1.0)["ok"] is True
