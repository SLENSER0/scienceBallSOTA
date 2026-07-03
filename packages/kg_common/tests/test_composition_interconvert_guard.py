"""Tests for the composition-unit family guard (§7.2).

RU: Тесты барьера неконвертируемых семейств единиц состава.
EN: Tests for the non-interconvertible composition-unit family guard.
"""

from __future__ import annotations

from kg_common.units.composition_interconvert_guard import (
    InterconvertVerdict,
    can_interconvert,
    composition_family,
)


def test_family_mass_fraction() -> None:
    assert composition_family("wt_percent") == "MASS_FRACTION"
    assert composition_family("wt%") == "MASS_FRACTION"
    assert composition_family("ppm") == "MASS_FRACTION"
    assert composition_family("ppb") == "MASS_FRACTION"


def test_family_atomic_fraction() -> None:
    assert composition_family("at_percent") == "ATOMIC_FRACTION"
    assert composition_family("at%") == "ATOMIC_FRACTION"
    assert composition_family("mol_percent") == "ATOMIC_FRACTION"


def test_family_non_composition_is_none() -> None:
    assert composition_family("MPa") is None
    assert composition_family("") is None


def test_within_mass_family_allowed() -> None:
    v = can_interconvert("wt_percent", "ppm")
    assert v.allowed is True
    assert v.family1 == "MASS_FRACTION"
    assert v.family2 == "MASS_FRACTION"


def test_ppm_ppb_allowed() -> None:
    assert can_interconvert("ppm", "ppb").allowed is True


def test_within_atomic_family_allowed() -> None:
    v = can_interconvert("at_percent", "mol_percent")
    assert v.allowed is True
    assert v.family1 == "ATOMIC_FRACTION"
    assert v.family2 == "ATOMIC_FRACTION"


def test_cross_family_forbidden() -> None:
    v = can_interconvert("wt_percent", "at_percent")
    assert v.allowed is False
    assert v.family1 == "MASS_FRACTION"
    assert v.family2 == "ATOMIC_FRACTION"


def test_non_composition_second_unit() -> None:
    v = can_interconvert("wt%", "MPa")
    assert v.family2 is None
    assert v.allowed is False
    assert "MPa" in v.reason


def test_non_composition_first_unit() -> None:
    v = can_interconvert("MPa", "ppm")
    assert v.family1 is None
    assert v.allowed is False


def test_verdict_as_dict_roundtrip() -> None:
    v = can_interconvert("wt_percent", "at_percent")
    d = v.as_dict()
    assert d == {
        "u1": "wt_percent",
        "u2": "at_percent",
        "family1": "MASS_FRACTION",
        "family2": "ATOMIC_FRACTION",
        "allowed": False,
        "reason": v.reason,
    }


def test_verdict_is_frozen() -> None:
    v = can_interconvert("ppm", "ppb")
    assert isinstance(v, InterconvertVerdict)
    try:
        v.allowed = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("InterconvertVerdict must be frozen")
