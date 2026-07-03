"""AMBIGUOUS_UNIT detection — bare %/ppm without a basis (§7.6)."""

from __future__ import annotations

from kg_extractors.unit_ambiguous import (
    AMBIGUOUS_UNIT,
    PERCENT_CANDIDATES,
    PPM_CANDIDATES,
    AmbiguityFlag,
    candidate_units,
    detect_ambiguous_unit,
)


def test_bare_percent_in_composition_is_ambiguous() -> None:
    """ "2.5 %" in a composition context is ambiguous with wt%/at% candidates (§7.6)."""
    flag = detect_ambiguous_unit("2.5 %", "composition")
    assert flag is not None
    assert flag.kind == AMBIGUOUS_UNIT
    assert flag.unit == "%"
    assert "wt%" in flag.candidates
    assert "at%" in flag.candidates


def test_qualified_wt_percent_is_not_ambiguous() -> None:
    """ "2.5 wt%" carries its basis explicitly → not ambiguous → None (§7.6)."""
    assert detect_ambiguous_unit("2.5 wt%", "composition") is None


def test_bare_ppm_without_basis_is_ambiguous() -> None:
    """A bare "50 ppm" has no mass/atomic/volume basis → ambiguous (§7.6)."""
    flag = detect_ambiguous_unit("50 ppm", "concentration")
    assert flag is not None
    assert flag.unit == "ppm"
    assert flag.candidates == ["wt ppm", "at ppm", "vol ppm"]


def test_mg_per_litre_is_not_ambiguous() -> None:
    """ "12 mg/L" is a fully-specified mass/volume unit → not ambiguous → None (§7.6)."""
    assert detect_ambiguous_unit("12 mg/L", "concentration") is None


def test_percent_in_recovery_context_is_not_ambiguous() -> None:
    """A percent in a non-composition (recovery) context is a plain % → None (§7.6)."""
    assert detect_ambiguous_unit("95 %", "recovery") is None


def test_candidate_units_lists_are_exact() -> None:
    """candidate_units returns the exact disambiguation lists (§7.6)."""
    assert candidate_units("%", "composition") == ["wt%", "at%", "vol%"]
    assert candidate_units("ppm", "composition") == ["wt ppm", "at ppm", "vol ppm"]
    # A qualified unit and a non-composition context both yield no candidates.
    assert candidate_units("wt%", "composition") == []
    assert candidate_units("%", "recovery") == []
    # Module constants agree with the produced candidates.
    assert list(PERCENT_CANDIDATES) == candidate_units("%", "composition")
    assert list(PPM_CANDIDATES) == candidate_units("ppm", "composition")


def test_as_dict_shape_and_values() -> None:
    """as_dict exposes kind/unit/candidates/reason with concrete values (§7.6)."""
    flag = detect_ambiguous_unit("2.5%", "composition")
    assert isinstance(flag, AmbiguityFlag)
    d = flag.as_dict()
    assert set(d.keys()) == {"kind", "unit", "candidates", "reason"}
    assert d["kind"] == "ambiguous_unit"
    assert d["unit"] == "%"
    assert d["candidates"] == ["wt%", "at%", "vol%"]
    assert "basis" in str(d["reason"])


def test_empty_string_is_none() -> None:
    """An empty (or blank) value string has no unit → None (§7.6)."""
    assert detect_ambiguous_unit("", "composition") is None
    assert detect_ambiguous_unit("   ", "composition") is None


def test_at_percent_and_ru_vol_percent_are_not_ambiguous() -> None:
    """Qualified "at%" and RU "об.%" (vol%) carry a basis → not ambiguous (§7.6)."""
    assert detect_ambiguous_unit("30 at%", "composition") is None
    assert detect_ambiguous_unit("30 об.%", "composition") is None


def test_ppmw_suffix_basis_is_not_ambiguous() -> None:
    """A weight-ppm suffix ("100 ppmw") is fully specified → not ambiguous (§7.6)."""
    assert detect_ambiguous_unit("100 ppmw", "composition") is None


def test_frozen_flag_is_immutable() -> None:
    """AmbiguityFlag is frozen — assignment raises (house style, §7.6)."""
    import dataclasses

    flag = detect_ambiguous_unit("2.5 %", "composition")
    assert flag is not None
    try:
        flag.unit = "wt%"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guard against a non-frozen regression
        raise AssertionError("AmbiguityFlag must be frozen")
