"""Deterministic numeric accuracy check (§18.10)."""

from __future__ import annotations

from kg_eval.numeric_check import NumericExpectation, check_numeric, extract_numbers


def test_extract_two_numbers_with_units() -> None:
    assert extract_numbers("hardness 120 HV at 180 C") == [(120.0, "HV"), (180.0, "C")]


def test_extract_thousands_separator() -> None:
    assert extract_numbers("1,200 MPa") == [(1200.0, "MPa")]


def test_extract_scientific() -> None:
    assert extract_numbers("1e3 K") == [(1000.0, "K")]


def test_extract_no_space_unit() -> None:
    assert extract_numbers("2.5h") == [(2.5, "h")]


def test_check_matched_exact() -> None:
    r = check_numeric("120 HV", NumericExpectation(120, "HV", tol=0.5))
    assert r.matched is True
    assert r.delta == 0.0
    assert r.best_value == 120.0


def test_check_abs_tol_not_matched() -> None:
    r = check_numeric("121 HV", NumericExpectation(120, "HV", tol=0.5))
    assert r.matched is False
    assert r.delta == 1.0


def test_check_relative_tol_matched() -> None:
    r = check_numeric("121 HV", NumericExpectation(120, "HV", tol=0.1, rel=True))
    assert r.matched is True
    assert r.delta == 1.0


def test_check_empty_text() -> None:
    r = check_numeric("no numbers here", NumericExpectation(120, "HV", tol=0.5))
    assert r.matched is False
    assert r.best_value is None
    assert r.delta is None


def test_as_dict_matched_is_bool() -> None:
    r = check_numeric("120 HV", NumericExpectation(120, "HV", tol=0.5))
    d = r.as_dict()
    assert isinstance(d["matched"], bool)
    assert d["best_value"] == 120.0
