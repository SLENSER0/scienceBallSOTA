"""Hardness scale conversion (§7.3)."""

from __future__ import annotations

import pytest

from kg_common.units import convert_hardness, hv_to_tensile_mpa


def test_identity_is_exact() -> None:
    c = convert_hardness(300, "HV", "HV")
    assert c.value == 300 and not c.approximate


def test_hv_hb_close_for_steel() -> None:
    # Brinell tracks slightly below Vickers on this table (HV 300 → HB ~285).
    c = convert_hardness(300, "HV", "HB")
    assert c.approximate and 275 <= c.value <= 295


def test_hv_to_hrc_monotonic() -> None:
    vals = [convert_hardness(hv, "HV", "HRC").value for hv in (300, 400, 500, 600)]
    assert vals == sorted(vals)  # harder → higher Rockwell-C
    assert 28 <= convert_hardness(300, "HV", "HRC").value <= 32  # anchor ≈30


def test_round_trip_is_approximately_stable() -> None:
    back = convert_hardness(convert_hardness(400, "HV", "HRC").value, "HRC", "HV").value
    assert abs(back - 400) <= 25  # interpolation round-trip within tolerance


def test_tensile_estimate_and_clamp() -> None:
    assert hv_to_tensile_mpa(300).value == pytest.approx(995, abs=5)
    # out-of-range clamps and flags in the note
    hi = hv_to_tensile_mpa(5000)
    assert "clamped" in hi.note


def test_unsupported_scale_raises() -> None:
    with pytest.raises(ValueError, match="unsupported hardness scale"):
        convert_hardness(300, "HV", "MOHS")
