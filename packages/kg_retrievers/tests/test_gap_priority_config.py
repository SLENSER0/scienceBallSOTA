"""Hand-checked tests for the §15.14 gap-priority weights + banding config.

Каждое ожидаемое значение задано конкретным числом/строкой по §15.14/§15.9.
Defaults: weights == §15.9 ``DEFAULT_WEIGHTS`` (sum 1.0), thresholds
``{"high": 0.66, "medium": 0.33}``.
"""

from __future__ import annotations

import pytest

from kg_retrievers.gap_priority_config import (
    DEFAULT_GAP_PRIORITY_THRESHOLDS,
    DEFAULT_GAP_PRIORITY_WEIGHTS,
    GapPriorityConfig,
    default_gap_priority_config,
)
from kg_retrievers.gap_scoring import DEFAULT_WEIGHTS, gap_priority_score

# ---------------------------------------------------------------------------
# Defaults (§15.14)
# ---------------------------------------------------------------------------


def test_defaults_match_spec() -> None:
    """default_gap_priority_config() → §15.9 weights + 0.66/0.33 band cut-offs."""
    cfg = default_gap_priority_config()
    assert cfg.weights == {
        "absence_confidence": 0.40,
        "importance": 0.25,
        "domain_criticality": 0.20,
        "novelty": 0.15,
    }
    assert cfg.weights == DEFAULT_WEIGHTS == DEFAULT_GAP_PRIORITY_WEIGHTS
    assert sum(cfg.weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert cfg.thresholds == {"high": 0.66, "medium": 0.33}
    assert cfg.thresholds == DEFAULT_GAP_PRIORITY_THRESHOLDS
    # A bare GapPriorityConfig() takes the same module defaults.
    assert cfg == GapPriorityConfig()


# ---------------------------------------------------------------------------
# from_dict override / defaults
# ---------------------------------------------------------------------------


def test_from_dict_override() -> None:
    """Every field overridden — none should keep its default."""
    cfg = GapPriorityConfig.from_dict(
        {
            "weights": {"absence_confidence": 0.5, "importance": 0.5},
            "thresholds": {"high": 0.8, "medium": 0.4},
        }
    )
    assert cfg.weights == {"absence_confidence": 0.5, "importance": 0.5}
    assert cfg.thresholds == {"high": 0.8, "medium": 0.4}


def test_from_dict_defaults_on_missing_keys() -> None:
    """from_dict({}) reproduces the full default config (§15.14)."""
    cfg = GapPriorityConfig.from_dict({})
    assert cfg.weights == DEFAULT_GAP_PRIORITY_WEIGHTS
    assert cfg.thresholds == DEFAULT_GAP_PRIORITY_THRESHOLDS
    assert cfg == default_gap_priority_config()


# ---------------------------------------------------------------------------
# band(score) → high / medium / low
# ---------------------------------------------------------------------------


def test_band_high_medium_low() -> None:
    """Default cut-offs 0.66 / 0.33 split the score into the three bands."""
    cfg = default_gap_priority_config()
    assert cfg.band(0.90) == "high"
    assert cfg.band(0.50) == "medium"
    assert cfg.band(0.10) == "low"


def test_band_boundaries_are_inclusive_lower_bounds() -> None:
    """A score exactly on a cut-off falls into the higher band (>= is inclusive)."""
    cfg = default_gap_priority_config()
    assert cfg.band(0.66) == "high"  # exactly at high cut-off
    assert cfg.band(0.6599) == "medium"  # just below high cut-off
    assert cfg.band(0.33) == "medium"  # exactly at medium cut-off
    assert cfg.band(0.3299) == "low"  # just below medium cut-off
    assert cfg.band(1.0) == "high"
    assert cfg.band(0.0) == "low"


def test_band_respects_custom_thresholds() -> None:
    """Custom cut-offs move the band boundaries accordingly."""
    cfg = GapPriorityConfig(thresholds={"high": 0.9, "medium": 0.5})
    assert cfg.band(0.95) == "high"
    assert cfg.band(0.7) == "medium"  # below 0.9 high, at/above 0.5 medium
    assert cfg.band(0.4) == "low"


# ---------------------------------------------------------------------------
# weights validation
# ---------------------------------------------------------------------------


def test_weights_validated() -> None:
    """Negative weights and an all-zero total are rejected (§15.14)."""
    with pytest.raises(ValueError, match="must be >= 0"):
        GapPriorityConfig(weights={"importance": -0.1, "absence_confidence": 0.5})
    with pytest.raises(ValueError, match="sum to a positive value"):
        GapPriorityConfig(weights={"importance": 0.0})
    with pytest.raises(ValueError, match="non-empty"):
        GapPriorityConfig(weights={})


def test_unknown_weight_rejected() -> None:
    """A weight key outside COMPONENT_NAMES raises ValueError (§15.14)."""
    with pytest.raises(ValueError, match="unknown weight 'bogus'"):
        GapPriorityConfig(weights={"bogus": 1.0})
    # A mix of a valid and an invalid key still rejects the whole config.
    with pytest.raises(ValueError, match="unknown weight"):
        GapPriorityConfig(weights={"importance": 0.5, "typo_signal": 0.5})


# ---------------------------------------------------------------------------
# thresholds validation / ordering
# ---------------------------------------------------------------------------


def test_thresholds_ordered() -> None:
    """high must be strictly greater than medium (§15.14)."""
    with pytest.raises(ValueError, match="ordered: high > medium"):
        GapPriorityConfig(thresholds={"high": 0.3, "medium": 0.5})
    with pytest.raises(ValueError, match="ordered: high > medium"):
        GapPriorityConfig(thresholds={"high": 0.4, "medium": 0.4})  # equal is not ordered
    # A correctly ordered pair is accepted.
    cfg = GapPriorityConfig(thresholds={"high": 0.7, "medium": 0.3})
    assert cfg.thresholds == {"high": 0.7, "medium": 0.3}


def test_threshold_out_of_range_rejected() -> None:
    """Cut-offs must lie in [0, 1]; missing keys raise (§15.14)."""
    with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
        GapPriorityConfig(thresholds={"high": 1.5, "medium": 0.3})
    with pytest.raises(ValueError, match="must contain 'medium'"):
        GapPriorityConfig(thresholds={"high": 0.7})
    with pytest.raises(ValueError, match="unknown threshold 'extreme'"):
        GapPriorityConfig(thresholds={"high": 0.7, "medium": 0.3, "extreme": 0.9})


# ---------------------------------------------------------------------------
# as_dict / from_dict round-trip
# ---------------------------------------------------------------------------


def test_as_dict_shape() -> None:
    """as_dict() exposes weights/thresholds as concrete plain values."""
    cfg = GapPriorityConfig(
        weights={"absence_confidence": 0.6, "novelty": 0.4},
        thresholds={"high": 0.75, "medium": 0.25},
    )
    assert cfg.as_dict() == {
        "weights": {"absence_confidence": 0.6, "novelty": 0.4},
        "thresholds": {"high": 0.75, "medium": 0.25},
    }


def test_as_dict_round_trip() -> None:
    """from_dict(as_dict(cfg)) == cfg (frozen dataclass value equality)."""
    cfg = GapPriorityConfig(
        weights={"importance": 0.3, "domain_criticality": 0.7},
        thresholds={"high": 0.8, "medium": 0.2},
    )
    assert GapPriorityConfig.from_dict(cfg.as_dict()) == cfg
    # The default config also survives a round-trip.
    default_cfg = default_gap_priority_config()
    assert GapPriorityConfig.from_dict(default_cfg.as_dict()) == default_cfg


# ---------------------------------------------------------------------------
# building ON gap_scoring (§15.9)
# ---------------------------------------------------------------------------


def test_score_delegates_to_gap_scoring() -> None:
    """config.score(gap) matches gap_priority_score with the config's weights (§15.9)."""
    cfg = default_gap_priority_config()
    # All four signals at 1.0 → weighted average is exactly 1.0 (band high).
    gap = {
        "absence_confidence": 1.0,
        "importance": 1.0,
        "domain": "water_treatment",  # domain_criticality prior == 1.0
        "novelty": 1.0,
    }
    assert cfg.score(gap) == 1.0
    assert cfg.score(gap) == gap_priority_score(gap, weights=cfg.weights)
    assert cfg.band_for(gap) == "high"


def test_band_for_low_priority_gap() -> None:
    """A weak, low-criticality gap scores 0.10 and lands in the 'low' band (§15.9)."""
    cfg = default_gap_priority_config()
    gap = {
        "absence_confidence": 0.0,
        "importance": 0.0,
        "domain": "general",  # domain_criticality prior == 0.5
        "novelty": 0.0,
    }
    # 0.40*0 + 0.25*0 + 0.20*0.5 + 0.15*0 = 0.10 (weights sum to 1.0).
    assert cfg.score(gap) == 0.10
    assert cfg.band_for(gap) == "low"


# ---------------------------------------------------------------------------
# immutability / defensive copy (house style)
# ---------------------------------------------------------------------------


def test_frozen_and_defensive_copy() -> None:
    """Config is frozen and owns private copies of the input dicts."""
    src_w = {"absence_confidence": 0.4, "importance": 0.6}
    src_t = {"high": 0.7, "medium": 0.3}
    cfg = GapPriorityConfig(weights=src_w, thresholds=src_t)
    src_w["absence_confidence"] = 999.0  # mutate caller's dicts → config unaffected
    src_t["high"] = 999.0
    assert cfg.weights == {"absence_confidence": 0.4, "importance": 0.6}
    assert cfg.thresholds == {"high": 0.7, "medium": 0.3}
    with pytest.raises(Exception):  # noqa: B017 - frozen assignment must fail
        cfg.weights = {}  # type: ignore[misc]
    # as_dict returns fresh copies — mutating them does not touch the config.
    out = cfg.as_dict()
    out["weights"]["absence_confidence"] = 0.0
    out["thresholds"]["high"] = 0.0
    assert cfg.weights["absence_confidence"] == 0.4
    assert cfg.thresholds["high"] == 0.7
