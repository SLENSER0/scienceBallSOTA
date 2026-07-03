"""Tests for §7.7 unit-scale repair suggestions (:mod:`kg_common.units.scale_repair`).

Hand-checkable against ``PROPERTY_UNIT_POLICY``:

* ``prop:tensile_strength`` typical band = [50, 4000] MPa.
* ``prop:hardness``          typical band = [20, 1200] HV.
"""

from __future__ import annotations

from kg_common.units.scale_repair import ScaleRepair, suggest_scale_repair


def test_low_value_scaled_up_by_1000() -> None:
    # 0.32 → ×1000 → 320 lands inside [50, 4000]; 0.32,3.2,32 all miss the band.
    r = suggest_scale_repair(0.32, "prop:tensile_strength")
    assert r.suggested_factor == 1000.0
    assert r.corrected_value == 320.0
    assert r.in_band is False


def test_high_value_scaled_down_by_thousandth() -> None:
    # 320000 → ×0.001 → 320 is the first factor that lands inside [50, 4000].
    r = suggest_scale_repair(320000, "prop:tensile_strength")
    assert r.suggested_factor == 0.001
    assert r.corrected_value == 320.0
    assert r.in_band is False


def test_value_already_in_band_factor_one() -> None:
    r = suggest_scale_repair(500, "prop:tensile_strength")
    assert r.in_band is True
    assert r.suggested_factor == 1.0
    assert r.corrected_value == 500.0


def test_out_of_band_flag() -> None:
    assert suggest_scale_repair(0.32, "prop:tensile_strength").in_band is False


def test_hardness_in_band() -> None:
    assert suggest_scale_repair(300, "prop:hardness").in_band is True


def test_frozen_dataclass_and_as_dict() -> None:
    r = suggest_scale_repair(0.32, "prop:tensile_strength")
    assert isinstance(r, ScaleRepair)
    d = r.as_dict()
    assert d == {
        "property_id": "prop:tensile_strength",
        "value": 0.32,
        "suggested_factor": 1000.0,
        "corrected_value": 320.0,
        "in_band": False,
        "reason": r.reason,
    }
    # frozen: fields are immutable.
    try:
        r.value = 1.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - dataclass(frozen=True) must forbid assignment
        raise AssertionError("ScaleRepair must be frozen")


def test_unknown_property_is_graceful() -> None:
    r = suggest_scale_repair(1.0, "prop:does_not_exist")
    assert r.suggested_factor == 1.0
    assert r.in_band is False
    assert r.corrected_value == 1.0


def test_reason_is_populated() -> None:
    assert suggest_scale_repair(0.32, "prop:tensile_strength").reason
    assert suggest_scale_repair(500, "prop:tensile_strength").reason
