"""Alloy-grade canonical-normalization tests (§6.17)."""

from __future__ import annotations

from kg_extractors.alloy_normalize import (
    NormalizedGrade,
    describe_grade,
    grade_family,
    normalize_grade,
)

# ---------------------------------------------------------------------------
# normalize_grade — canonical token
# ---------------------------------------------------------------------------


def test_normalize_2024_t6_canonical() -> None:
    assert normalize_grade("2024-t6") == "AA2024-T6"


def test_normalize_aa2024_no_temper() -> None:
    assert normalize_grade("AA2024") == "AA2024"


def test_normalize_6061_t651_temper() -> None:
    assert normalize_grade("Plate of 6061-T651 was machined.") == "AA6061-T651"


def test_normalize_inconel_718() -> None:
    assert normalize_grade("inconel 718") == "INCONEL718"


def test_normalize_ti_6al_4v_preserves_symbols() -> None:
    assert normalize_grade("Ti-6Al-4V") == "Ti-6Al-4V"


def test_normalize_316l_stainless() -> None:
    assert normalize_grade("316L") == "316L"


def test_normalize_unknown_is_none() -> None:
    assert normalize_grade("A polished specimen under the microscope.") is None
    assert normalize_grade("") is None


# ---------------------------------------------------------------------------
# grade_family — broad alloy family
# ---------------------------------------------------------------------------


def test_family_aluminium_for_aa2024() -> None:
    assert grade_family("AA2024") == "aluminium"


def test_family_nickel_for_inconel() -> None:
    assert grade_family("Inconel 718") == "nickel"


def test_family_titanium_for_ti_6al_4v() -> None:
    assert grade_family("Ti-6Al-4V") == "titanium"


def test_family_steel_for_316l() -> None:
    assert grade_family("316L") == "steel"


def test_family_unknown_is_none() -> None:
    assert grade_family("just a plain rock") is None


# ---------------------------------------------------------------------------
# idempotence + structured describe_grade
# ---------------------------------------------------------------------------


def test_normalize_is_idempotent() -> None:
    for surface in ("2024-t6", "AA2024", "inconel 718", "Ti-6Al-4V", "316L"):
        once = normalize_grade(surface)
        assert once is not None
        assert normalize_grade(once) == once


def test_describe_grade_dataclass_and_as_dict() -> None:
    ng = describe_grade("2024-t6")
    assert ng == NormalizedGrade(canonical="AA2024-T6", family="aluminium", system="AA")
    assert ng.as_dict() == {
        "canonical": "AA2024-T6",
        "family": "aluminium",
        "system": "AA",
    }
    assert describe_grade("no grade here") is None
