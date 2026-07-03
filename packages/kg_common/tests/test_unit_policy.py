"""Property-unit policy + physical-range validation (§7.2 / §7.7)."""

from __future__ import annotations

from kg_common.units.policy import (
    PROPERTY_UNIT_POLICY,
    RangeResult,
    UnitCheck,
    allowed_units,
    is_unit_allowed,
    unit_ok_for,
    validate_range,
)


def test_allowed_units_hardness_exact() -> None:
    # §7.2: hardness carries the three metallurgy scales, canonical HV.
    assert allowed_units("prop:hardness") == ("HV", "HB", "HRC")
    assert PROPERTY_UNIT_POLICY["prop:hardness"]["canonical_unit"] == "HV"


def test_is_unit_allowed_true_and_false() -> None:
    assert is_unit_allowed("prop:hardness", "HB") is True
    # a strength unit is not a valid hardness unit
    assert is_unit_allowed("prop:hardness", "MPa") is False


def test_unit_matching_is_case_and_format_folded() -> None:
    # 'A/m^2' policy key must match plain, superscript and lowercase spellings.
    assert is_unit_allowed("prop:current_density", "A/m^2") is True
    assert is_unit_allowed("prop:current_density", "A/m2") is True
    assert is_unit_allowed("prop:current_density", "a/m²") is True
    assert is_unit_allowed("prop:hardness", "hv") is True  # case-fold


def test_in_range_value_is_ok() -> None:
    # 250 HV is a normal steel hardness → severity "ok".
    r = validate_range("prop:hardness", 250)
    assert r.ok is True and r.severity == "ok"


def test_absurd_hardness_is_error() -> None:
    # 100000 HV is physically impossible → hard error, not merely a warning.
    r = validate_range("prop:hardness", 100000)
    assert r.ok is False and r.severity == "error"
    assert "above physical maximum" in r.reason and "HV" in r.reason


def test_outlier_within_hard_bounds_is_warning() -> None:
    # 1500 HV is below the 2000 hard cap but above the 1200 typical band.
    r = validate_range("prop:hardness", 1500)
    assert r.ok is True and r.severity == "warning" and "outlier" in r.reason


def test_percent_zero_to_hundred_bounds() -> None:
    assert validate_range("prop:recovery", 50).severity == "ok"
    over = validate_range("prop:recovery", 150)
    assert over.ok is False and over.severity == "error"
    under = validate_range("prop:removal_efficiency", -5)
    assert under.ok is False and under.severity == "error"


def test_ph_is_unitless_and_bounded() -> None:
    # pH accepts "no unit" but rejects a real unit; value bounded to 0..14.
    assert is_unit_allowed("prop:ph", None) is True
    assert is_unit_allowed("prop:ph", "") is True
    assert is_unit_allowed("prop:ph", "MPa") is False
    assert validate_range("prop:ph", 7).severity == "ok"
    assert validate_range("prop:ph", 15).severity == "error"
    assert validate_range("prop:ph", -1).severity == "error"


def test_temperature_below_absolute_zero_is_error() -> None:
    # -300 °C is below absolute zero (-273.15) → error.
    r = validate_range("prop:temperature", -300)
    assert r.ok is False and r.severity == "error"
    assert validate_range("prop:temperature", 25).severity == "ok"


def test_unknown_property_is_graceful() -> None:
    assert allowed_units("prop:does_not_exist") == ()
    assert is_unit_allowed("prop:does_not_exist", "MPa") is False
    r = validate_range("prop:does_not_exist", 5)
    assert r.ok is True and r.severity == "unknown"
    uc = unit_ok_for("prop:does_not_exist", "MPa")
    assert uc.ok is True and uc.severity == "unknown"


def test_unit_ok_for_structured_result() -> None:
    ok = unit_ok_for("prop:tensile_strength", "MPa")
    assert isinstance(ok, UnitCheck)
    assert ok.ok is True and ok.canonical_unit == "MPa" and ok.severity == "ok"
    bad = unit_ok_for("prop:tensile_strength", "HV")
    assert bad.ok is False and bad.severity == "error"
    d = bad.as_dict()
    assert d["ok"] is False and d["canonical_unit"] == "MPa"
    assert "not allowed" in d["reason"]


def test_range_result_as_dict_shape() -> None:
    r = validate_range("prop:tds", 800)
    assert isinstance(r, RangeResult)
    d = r.as_dict()
    assert set(d) == {"ok", "reason", "severity"}
    assert d["severity"] == "ok"  # 800 mg/L is ordinary process water
    # brine well above the typical band but below the hard cap → warning
    assert validate_range("prop:tds", 200000).severity == "warning"


def test_non_numeric_value_is_rejected() -> None:
    r = validate_range("prop:voltage", None)
    assert r.ok is False and r.severity == "error"
    assert validate_range("prop:voltage", "abc").severity == "error"
