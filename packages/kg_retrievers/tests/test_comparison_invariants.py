"""Hand-checked tests for comparison invariants (§24.13).

Concrete expectations verified against ``kg_extractors.units.to_canonical``:
- ``MPa`` and Cyrillic ``МПа`` both canonicalise to ``bar`` (magnitude ×10) →
  compatible; ``HV`` is unknown to the registry (→ ``None``) → not compatible with
  the dimensioned ``MPa``; ``200 MPa`` == ``2000 bar``.
"""

from __future__ import annotations

import pytest

from kg_retrievers.comparison_invariants import (
    ComparabilityResult,
    ComparisonError,
    InvariantViolation,
    check_comparable,
    enforce_invariants,
    safe_compare,
)


def test_same_property_same_unit_is_comparable() -> None:
    a = {"property_id": "tensile_strength", "unit": "MPa", "value": 200}
    b = {"property_id": "tensile_strength", "unit": "MPa", "value": 300}
    res = check_comparable(a, b)
    assert isinstance(res, ComparabilityResult)
    assert res.comparable is True
    assert "comparable" in res.reason


def test_different_property_not_comparable_with_reason() -> None:
    a = {"property_id": "tensile_strength", "unit": "MPa"}
    b = {"property_id": "hardness", "unit": "MPa"}
    res = check_comparable(a, b)
    assert res.comparable is False
    assert "property" in res.reason
    assert "tensile_strength" in res.reason and "hardness" in res.reason


def test_convertible_units_mpa_vs_cyrillic_mpa_are_comparable() -> None:
    # 'MPa' and 'МПа' (Cyrillic) both canonicalise to 'bar' → compatible.
    a = {"property_id": "yield_strength", "unit": "MPa"}
    b = {"property_id": "yield_strength", "unit": "МПа"}
    res = check_comparable(a, b)
    assert res.comparable is True
    assert res.reason.startswith("comparable")


def test_incompatible_units_hv_vs_mpa_not_comparable() -> None:
    # 'HV' (Vickers hardness) is unknown to the unit registry → not comparable
    # with the dimensioned 'MPa', even under the same property id.
    a = {"property_id": "hardness", "unit": "HV"}
    b = {"property_id": "hardness", "unit": "MPa"}
    res = check_comparable(a, b)
    assert res.comparable is False
    assert "unit" in res.reason
    assert "'HV'" in res.reason and "'MPa'" in res.reason


def test_missing_property_not_comparable() -> None:
    a = {"unit": "MPa"}  # no property_id
    b = {"property_id": "tensile_strength", "unit": "MPa"}
    res = check_comparable(a, b)
    assert res.comparable is False
    assert "property" in res.reason
    # blank / null property ids are treated as missing too
    assert check_comparable({"property_id": "  ", "unit": "MPa"}, b).comparable is False
    assert check_comparable({"property_id": None, "unit": "MPa"}, b).comparable is False


def test_safe_compare_raises_on_property_mismatch() -> None:
    a = {"property_id": "tensile_strength", "unit": "MPa", "value": 10}
    b = {"property_id": "hardness", "unit": "MPa", "value": 10}
    with pytest.raises(ComparisonError):
        safe_compare(a, b)


def test_safe_compare_raises_on_unit_mismatch() -> None:
    a = {"property_id": "hardness", "unit": "HV", "value": 350}
    b = {"property_id": "hardness", "unit": "MPa", "value": 350}
    with pytest.raises(ComparisonError):
        safe_compare(a, b)


def test_safe_compare_orders_in_canonical_units() -> None:
    # 200 MPa == 2000 bar  <  300 MPa == 3000 bar → a < b → -1.
    a = {"property_id": "tensile_strength", "unit": "MPa", "value": 200}
    b = {"property_id": "tensile_strength", "unit": "MPa", "value": 300}
    assert safe_compare(a, b) == -1
    assert safe_compare(b, a) == 1
    # 1 MPa == 10 bar  >  5 bar → 1 (cross-unit compare after canonicalisation).
    c = {"property_id": "tensile_strength", "unit": "MPa", "value": 1}
    d = {"property_id": "tensile_strength", "unit": "bar", "value": 5}
    assert safe_compare(c, d) == 1
    # 200 MPa == 2000 bar → equal → 0.
    e = {"property_id": "tensile_strength", "unit": "bar", "value": 2000}
    assert safe_compare(a, e) == 0


def test_enforce_invariants_flags_the_bad_pair_only() -> None:
    rows = [
        {"property_id": "tensile_strength", "unit": "MPa"},  # 0
        {"property_id": "tensile_strength", "unit": "МПа"},  # 1 compatible with 0
        {"property_id": "hardness", "unit": "HV"},  # 2 different property → not flagged
        {"property_id": "hardness", "unit": "MPa"},  # 3 same prop as 2, bad unit → BAD
    ]
    violations = enforce_invariants(rows)
    assert len(violations) == 1
    bad = violations[0]
    assert isinstance(bad, InvariantViolation)
    assert (bad.i, bad.j) == (2, 3)
    assert bad.property_id == "hardness"
    assert "unit" in bad.reason


def test_comparability_result_as_dict_roundtrip() -> None:
    res = check_comparable(
        {"property_id": "p", "unit": "MPa"},
        {"property_id": "p", "unit": "MPa"},
    )
    assert res.as_dict() == {"comparable": True, "reason": res.reason}
    bad = enforce_invariants(
        [
            {"property_id": "p", "unit": "HV"},
            {"property_id": "p", "unit": "MPa"},
        ]
    )[0]
    assert bad.as_dict() == {
        "i": 0,
        "j": 1,
        "property_id": "p",
        "reason": bad.reason,
    }
