"""Tests for effect magnitude banding (§6.6).

Проверки полос величины эффекта: значения посчитаны вручную.
"""

from __future__ import annotations

from kg_extractors.effect_magnitude import EffectMagnitude, classify_magnitude


def test_large_increase() -> None:
    # (148-100)/100*100 = 48.0 %, abs>20 -> large, value>baseline -> increase.
    m = classify_magnitude(100, 148)
    assert m.pct_change == 48.0
    assert m.band == "large"
    assert m.direction == "increase"


def test_marginal_band() -> None:
    # 3.0 % -> above negligible_max(1) but <= marginal_max(5) -> marginal.
    assert classify_magnitude(100, 103).band == "marginal"


def test_negligible_reads_no_change() -> None:
    # 0.5 % -> <= negligible_max(1) -> negligible, direction forced to no_change.
    c = classify_magnitude(100, 100.5)
    assert c.band == "negligible"
    assert c.direction == "no_change"


def test_moderate_decrease() -> None:
    # (85-100)/100*100 = -15.0 %, abs<=20 -> moderate, value<baseline -> decrease.
    d = classify_magnitude(100, 85)
    assert d.direction == "decrease"
    assert d.band == "moderate"


def test_zero_baseline_is_unknown() -> None:
    z = classify_magnitude(0, 50)
    assert z.pct_change is None
    assert z.band == "unknown"
    assert z.direction == "unknown"


def test_as_dict_keys() -> None:
    m = classify_magnitude(100, 148)
    assert set(m.as_dict()) == {"pct_change", "band", "direction"}


def test_as_dict_values_roundtrip() -> None:
    z = classify_magnitude(0, 50)
    assert z.as_dict() == {"pct_change": None, "band": "unknown", "direction": "unknown"}


def test_boundary_negligible_inclusive() -> None:
    # Exactly negligible_max(1 %) -> still negligible / no_change.
    b = classify_magnitude(100, 101)
    assert b.band == "negligible"
    assert b.direction == "no_change"


def test_boundary_moderate_inclusive() -> None:
    # Exactly moderate_max(20 %) -> moderate, not large.
    b = classify_magnitude(100, 120)
    assert b.band == "moderate"
    assert b.direction == "increase"


def test_custom_thresholds() -> None:
    # Widen negligible band so a 4 % change reads as negligible/no_change.
    m = classify_magnitude(100, 104, negligible_max=5.0)
    assert m.band == "negligible"
    assert m.direction == "no_change"


def test_frozen_dataclass() -> None:
    m = classify_magnitude(100, 148)
    assert isinstance(m, EffectMagnitude)
    try:
        m.band = "moderate"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen must raise
        raise AssertionError("EffectMagnitude must be frozen")
