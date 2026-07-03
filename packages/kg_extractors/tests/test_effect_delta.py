"""Tests for baseline→value effect delta (§6.6)."""

from __future__ import annotations

from kg_extractors.effect_delta import EffectDelta, compute_effect_delta


def test_increase_abs_and_pct() -> None:
    # 90 HV → 148 HV: +58 absolute, +64.44 % relative (90 → 148 = 64.44 %).
    d = compute_effect_delta(90, 148)
    assert d.abs_change == 58.0
    assert d.pct_change is not None
    assert round(d.pct_change, 2) == 64.44
    assert d.direction == "increase"
    assert d.consistent is True


def test_decrease_pct_is_exact_negative() -> None:
    # 200 → 150 is a clean -25 %.
    d = compute_effect_delta(200, 150)
    assert d.direction == "decrease"
    assert d.pct_change == -25.0
    assert d.abs_change == -50.0


def test_no_change_equal_values() -> None:
    d = compute_effect_delta(100, 100)
    assert d.direction == "no_change"
    assert d.abs_change == 0.0
    assert d.pct_change == 0.0


def test_stated_direction_contradicts_derived() -> None:
    # Numbers rose but the text claimed a decrease → inconsistent.
    d = compute_effect_delta(90, 148, "decrease")
    assert d.direction == "increase"
    assert d.direction_stated == "decrease"
    assert d.consistent is False


def test_stated_direction_agrees() -> None:
    d = compute_effect_delta(90, 148, "increase")
    assert d.consistent is True


def test_zero_baseline_pct_is_none() -> None:
    d = compute_effect_delta(0, 50)
    assert d.pct_change is None
    assert d.abs_change == 50.0
    assert d.direction == "increase"


def test_tolerance_dead_band_reads_as_no_change() -> None:
    # A drift of 1e-7 with a 1e-3 dead-band is negligible → no_change.
    d = compute_effect_delta(100, 100.0000001, no_change_tol=1e-3)
    assert d.direction == "no_change"


def test_tolerance_tight_default_registers_change() -> None:
    d = compute_effect_delta(100, 100.0000001)
    assert d.direction == "increase"


def test_as_dict_shape_and_bool() -> None:
    d = compute_effect_delta(90, 148, "decrease")
    out = d.as_dict()
    assert isinstance(out["consistent"], bool)
    assert out["consistent"] is False
    assert out["abs_change"] == 58.0
    assert out["direction"] == "increase"
    assert out["direction_stated"] == "decrease"
    assert set(out) == {
        "baseline",
        "value",
        "abs_change",
        "pct_change",
        "direction",
        "direction_stated",
        "consistent",
    }


def test_frozen_dataclass_immutable() -> None:
    d = compute_effect_delta(90, 148)
    assert isinstance(d, EffectDelta)
    try:
        d.value = 1.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("EffectDelta should be frozen")
