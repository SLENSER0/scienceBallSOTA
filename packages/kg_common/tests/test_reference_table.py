"""Tests for the §7.8 reference conversion-table harness — сверка (§7.8)."""

from __future__ import annotations

from kg_common.units.reference_table import (
    REFERENCE_CASES,
    ReferenceCase,
    run_reference_table,
)


def _find(from_unit: str, to_unit: str) -> ReferenceCase:
    """Locate the single case matching a (from_unit, to_unit) pair."""
    matches = [c for c in REFERENCE_CASES if c.from_unit == from_unit and c.to_unit == to_unit]
    assert len(matches) == 1, f"expected one case for {from_unit}->{to_unit}, got {len(matches)}"
    return matches[0]


def _report(from_unit: str, to_unit: str) -> dict[str, object]:
    """Locate the run report for a (from_unit, to_unit) pair."""
    for report in run_reference_table():
        case = report["case"]
        assert isinstance(case, dict)
        if case["from_unit"] == from_unit and case["to_unit"] == to_unit:
            return report
    raise AssertionError(f"no report for {from_unit}->{to_unit}")


def test_all_reference_rows_pass() -> None:
    """Every live converter reproduces its §7.8 doc row within tolerance."""
    reports = run_reference_table()
    assert reports, "harness produced no reports"
    assert all(r["ok"] for r in reports)


def test_table_has_at_least_ten_rows() -> None:
    """§7.8 defines a multi-row table; the harness must carry >=10 of them."""
    assert len(REFERENCE_CASES) >= 10


def test_every_case_has_positive_tolerance() -> None:
    """A zero/negative tolerance would make a row un-checkable or vacuous."""
    for case in REFERENCE_CASES:
        assert case.tolerance > 0, f"non-positive tolerance on {case}"


def test_ksi_to_mpa_row_matches_datasheet_constant() -> None:
    """1 ksi → MPa lands within 1e-4 of the datasheet 6.894757 figure."""
    report = _report("ksi", "MPa")
    got = report["got"]
    assert isinstance(got, float)
    assert abs(got - 6.894757) < 1e-4
    assert report["ok"] is True


def test_ninety_minutes_to_hours_is_exactly_one_and_a_half() -> None:
    """90 min → h is an exact rational: got must equal 1.5 with no drift."""
    report = _report("min", "h")
    assert report["got"] == 1.5
    assert report["ok"] is True


def test_hrc_to_hv_row_is_ok_within_ten() -> None:
    """30 HRC → HV is approximate; the row's ±10 band must still pass."""
    case = _find("HRC", "HV")
    assert case.dimension == "hardness"
    assert case.tolerance == 10.0
    report = _report("HRC", "HV")
    got = report["got"]
    assert isinstance(got, float)
    assert abs(got - case.expected) <= case.tolerance
    assert report["ok"] is True


def test_temperature_and_length_rows_present_and_pass() -> None:
    """Spot-check the affine (degC->K) and linear (nm->um) dispatch paths."""
    deg = _report("degC", "K")
    assert deg["got"] == 453.15
    assert deg["ok"] is True
    length = _report("nm", "um")
    assert length["got"] == 1.0
    assert length["ok"] is True


def test_cases_round_trip_through_as_dict() -> None:
    """Each REFERENCE_CASES entry survives an as_dict() round trip."""
    for case in REFERENCE_CASES:
        payload = case.as_dict()
        assert payload == {
            "from_value": case.from_value,
            "from_unit": case.from_unit,
            "to_unit": case.to_unit,
            "expected": case.expected,
            "tolerance": case.tolerance,
            "dimension": case.dimension,
        }
        assert ReferenceCase(**payload) == case  # type: ignore[arg-type]


def test_report_shape_is_case_got_ok() -> None:
    """Each report exposes exactly the {case, got, ok} contract."""
    for report in run_reference_table():
        assert set(report) == {"case", "got", "ok"}
        assert isinstance(report["case"], dict)
        assert isinstance(report["got"], float)
        assert isinstance(report["ok"], bool)
