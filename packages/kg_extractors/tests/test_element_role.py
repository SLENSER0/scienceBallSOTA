"""Tests for element role classification in compositions (§6.4)."""

from __future__ import annotations

from kg_extractors.element_role import (
    ElementRole,
    classify_roles,
)


def test_default_banding_al_cu_mg() -> None:
    # Al matrix, Cu major addition (4.0 >= 1.0), Mg minor (0.5 >= 0.1).
    roles = classify_roles({"Al": 95.5, "Cu": 4.0, "Mg": 0.5})
    assert [(r.element, r.role) for r in roles] == [
        ("Al", "base"),
        ("Cu", "major"),
        ("Mg", "minor"),
    ]


def test_sorted_by_fraction_desc() -> None:
    roles = classify_roles({"Mg": 0.5, "Al": 95.5, "Cu": 4.0})
    assert [r.fraction for r in roles] == [95.5, 4.0, 0.5]


def test_explicit_base_placed_first() -> None:
    # Cu is the explicit base even though Al has the larger fraction.
    roles = classify_roles({"Al": 95.5, "Cu": 4.0}, base="Cu")
    assert roles[0].element == "Cu"
    cu = next(r for r in roles if r.element == "Cu")
    assert cu.role == "base"
    # The non-base high-fraction element still bands as major.
    al = next(r for r in roles if r.element == "Al")
    assert al.role == "major"


def test_single_element_is_base() -> None:
    # A lone element is the base regardless of how small its fraction is.
    roles = classify_roles({"Fe": 0.05})
    assert [r.role for r in roles] == ["base"]
    assert roles[0].fraction == 0.05


def test_trace_band_below_minor_min() -> None:
    # Fe at 0.05 is below minor_min (0.1) -> trace.
    roles = classify_roles({"Al": 99.0, "Fe": 0.05})
    assert [r.role for r in roles][1] == "trace"
    assert roles[1].element == "Fe"


def test_empty_mapping() -> None:
    assert classify_roles({}) == []


def test_as_dict_keys() -> None:
    role = classify_roles({"Al": 100.0})[0]
    assert set(role.as_dict()) == {"element", "fraction", "role"}
    assert role.as_dict() == {"element": "Al", "fraction": 100.0, "role": "base"}


def test_custom_thresholds() -> None:
    # Raise major_min above Cu's fraction -> Cu demotes from major to minor.
    roles = classify_roles({"Al": 95.5, "Cu": 4.0, "Mg": 0.5}, major_min=5.0)
    by_el = {r.element: r.role for r in roles}
    assert by_el == {"Al": "base", "Cu": "minor", "Mg": "minor"}


def test_explicit_base_absent_falls_back_to_max() -> None:
    # base names an element not in the mapping -> fall back to max fraction.
    roles = classify_roles({"Al": 90.0, "Zn": 10.0}, base="Ti")
    assert roles[0].element == "Al"
    assert roles[0].role == "base"


def test_element_role_frozen_dataclass() -> None:
    role = ElementRole(element="Cr", fraction=18.0, role="major")
    assert role.as_dict() == {
        "element": "Cr",
        "fraction": 18.0,
        "role": "major",
    }
    # Frozen: attributes cannot be reassigned.
    try:
        role.role = "minor"  # type: ignore[misc]
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:  # pragma: no cover - guard against a non-frozen regression
        raise AssertionError("ElementRole should be frozen")
