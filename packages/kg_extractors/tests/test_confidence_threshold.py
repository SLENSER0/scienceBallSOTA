"""Tests for §16.5 ``low_confidence`` threshold resolver — hand-checked values."""

from __future__ import annotations

from kg_extractors.confidence_threshold import (
    DEFAULT_THRESHOLD,
    ThresholdConfig,
    ThresholdDecision,
    is_low_confidence,
    resolve_threshold,
)


def test_resolve_default() -> None:
    """No override → the default threshold 0.65 (§16.5)."""
    cfg = ThresholdConfig()
    assert cfg.default == DEFAULT_THRESHOLD == 0.65
    assert resolve_threshold(cfg, "table", "x") == 0.65


def test_resolve_by_source() -> None:
    """A by_source override applies to its source type (§16.5)."""
    cfg = ThresholdConfig(by_source={"table": 0.8})
    assert resolve_threshold(cfg, "table", "x") == 0.8
    # Unlisted source falls back to default.
    assert resolve_threshold(cfg, "text", "x") == 0.65


def test_resolve_property_beats_source() -> None:
    """by_property wins over by_source on conflict (свойство важнее, §16.5)."""
    cfg = ThresholdConfig(by_source={"table": 0.8}, by_property={"value": 0.9})
    # 'value' property override beats the 'table' source override.
    assert resolve_threshold(cfg, "table", "value") == 0.9
    # A property with no override still uses the source override.
    assert resolve_threshold(cfg, "table", "unit") == 0.8


def test_resolve_property_beats_default() -> None:
    """by_property override applies even without any source override (§16.5)."""
    cfg = ThresholdConfig(by_property={"value": 0.9})
    assert resolve_threshold(cfg, "figure", "value") == 0.9
    assert resolve_threshold(cfg, "figure", "other") == 0.65


def test_low_confidence_above_threshold() -> None:
    """0.7 vs default 0.65 → not below (§16.5)."""
    cfg = ThresholdConfig()
    decision = is_low_confidence(cfg, 0.7, "table", "x")
    assert decision.below is False
    assert decision.threshold == 0.65
    assert decision.confidence == 0.7
    assert decision.source_type == "table"
    assert decision.property_name == "x"


def test_low_confidence_below_threshold() -> None:
    """0.5 vs default 0.65 → below (§16.5)."""
    cfg = ThresholdConfig()
    decision = is_low_confidence(cfg, 0.5, "table", "x")
    assert decision.below is True
    assert decision.threshold == 0.65


def test_threshold_echoes_resolver() -> None:
    """Decision.threshold equals resolve_threshold for the same inputs (§16.5)."""
    cfg = ThresholdConfig(by_source={"table": 0.8}, by_property={"value": 0.9})
    for source_type, prop in [("table", "value"), ("table", "unit"), ("text", "x")]:
        decision = is_low_confidence(cfg, 0.7, source_type, prop)
        assert decision.threshold == resolve_threshold(cfg, source_type, prop)


def test_boundary_equal_is_not_below() -> None:
    """confidence == threshold → not below (граничный случай, §16.5)."""
    cfg = ThresholdConfig()
    decision = is_low_confidence(cfg, 0.65, "table", "x")
    assert decision.threshold == 0.65
    assert decision.below is False


def test_boundary_with_override() -> None:
    """Boundary against a resolved override threshold, not the default (§16.5)."""
    cfg = ThresholdConfig(by_source={"table": 0.8})
    # 0.8 exactly on the override threshold → not below.
    assert is_low_confidence(cfg, 0.8, "table", "x").below is False
    # 0.7 sits below the 0.8 override (but would be above the 0.65 default).
    assert is_low_confidence(cfg, 0.7, "table", "x").below is True


def test_as_dict_below_is_bool() -> None:
    """as_dict()['below'] is a real bool; dict carries all fields (§16.5)."""
    cfg = ThresholdConfig()
    decision = is_low_confidence(cfg, 0.5, "table", "x")
    data = decision.as_dict()
    assert isinstance(data["below"], bool)
    assert data == {
        "confidence": 0.5,
        "threshold": 0.65,
        "below": True,
        "source_type": "table",
        "property_name": "x",
    }


def test_decision_is_frozen() -> None:
    """ThresholdDecision is a frozen dataclass (§16.5)."""
    decision = ThresholdDecision(0.5, 0.65, True, "table", "x")
    try:
        decision.below = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - would indicate a mutable dataclass
        raise AssertionError("ThresholdDecision should be frozen")


def test_config_as_dict() -> None:
    """ThresholdConfig.as_dict() reflects overrides (§16.5)."""
    cfg = ThresholdConfig(by_source={"table": 0.8}, by_property={"value": 0.9})
    assert cfg.as_dict() == {
        "default": 0.65,
        "by_source": {"table": 0.8},
        "by_property": {"value": 0.9},
    }
