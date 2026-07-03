"""§6.16 multi-extractor confidence fusion — hand-checked cases."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.extraction_confidence import (
    METHOD_NOISY_OR,
    METHOD_WEIGHTED_MEAN,
    CombinedConfidence,
    agreement_boost,
    combine_layers,
    noisy_or,
)


def test_noisy_or_of_two_halves_is_0_75() -> None:
    # 1 - (1-0.5)(1-0.5) = 1 - 0.25 = 0.75.
    assert noisy_or([0.5, 0.5]) == 0.75


def test_noisy_or_empty_and_single() -> None:
    assert noisy_or([]) == 0.0  # no layer fired
    assert noisy_or([0.7]) == 0.7  # single value passes through


def test_single_layer_passthrough() -> None:
    c = combine_layers(ml=0.7)
    assert c.value == 0.7  # one layer → no fusion, no boost
    assert c.sources == ["ml"]
    assert c.method == METHOD_WEIGHTED_MEAN


def test_weighted_mean_of_two_layers() -> None:
    # Spread 0.5 > tol → no agreement boost, pure weighted mean.
    # (1·0.4 + 3·0.9) / (1 + 3) = 3.1 / 4 = 0.775.
    c = combine_layers(rule=0.4, ml=0.9, weights={"rule": 1.0, "ml": 3.0})
    assert c.value == 0.775
    assert c.sources == ["rule", "ml"]
    assert c.method == METHOD_WEIGHTED_MEAN


def test_weighted_mean_default_equal_weights() -> None:
    # Spread 0.4 > tol → no boost; equal weights → plain mean (0.4+0.8)/2 = 0.6.
    c = combine_layers(rule=0.4, ml=0.8)
    assert c.value == 0.6


def test_all_none_is_zero() -> None:
    c = combine_layers()
    assert c.value == 0.0
    assert c.sources == []
    assert c.method == METHOD_WEIGHTED_MEAN


def test_agreement_of_rule_and_ml_boosts_vs_single() -> None:
    # Two agreeing layers (spread 0 <= tol): 0.6 + 0.1·1·(1-0.6) = 0.64.
    both = combine_layers(rule=0.6, ml=0.6)
    single = combine_layers(rule=0.6)
    assert both.value == 0.64
    assert single.value == 0.6
    assert both.value > single.value


def test_disagreeing_layers_get_no_boost() -> None:
    # Spread 0.7 > tol → no boost; equal-weight mean (0.9+0.2)/2 = 0.55.
    c = combine_layers(rule=0.9, ml=0.2)
    assert c.value == 0.55


def test_agreement_boost_helper_needs_two() -> None:
    assert agreement_boost(0.6, 1) == 0.6  # single agree → unchanged
    assert agreement_boost(0.6, 2) == 0.64  # 0.6 + 0.1·(1-0.6)
    assert agreement_boost(0.6, 3) == 0.68  # 0.6 + 0.2·(1-0.6)


def test_value_bounded_0_1() -> None:
    # Out-of-range inputs are clamped before fusing → result stays in [0, 1].
    c = combine_layers(rule=1.5, ml=-0.3)  # → clamp to 1.0 and 0.0
    assert 0.0 <= c.value <= 1.0
    assert c.value == 0.5  # spread 1.0 > tol → no boost, mean of 1.0 & 0.0
    # Noisy-OR of near-certain agreeing layers must not exceed 1.0.
    assert 0.0 <= noisy_or([0.9, 0.9, 0.9]) <= 1.0


def test_sources_list_which_layers() -> None:
    c = combine_layers(rule=0.5, llm=0.8)  # ml absent
    assert c.sources == ["rule", "llm"]  # canonical order, ml omitted


def test_as_dict_has_three_fields() -> None:
    c = combine_layers(rule=0.6, ml=0.6)
    assert c.as_dict() == {
        "value": 0.64,
        "sources": ["rule", "ml"],
        "method": METHOD_WEIGHTED_MEAN,
    }


def test_noisy_or_method_option() -> None:
    # Base noisy-OR 0.75, then agreement boost (spread 0): 0.75 + 0.1·(1-0.75).
    c = combine_layers(rule=0.5, ml=0.5, method=METHOD_NOISY_OR)
    assert c.value == 0.775
    assert c.method == METHOD_NOISY_OR
    assert c.sources == ["rule", "ml"]


def test_unknown_method_raises() -> None:
    with pytest.raises(ValueError):
        combine_layers(rule=0.5, method="median")


def test_frozen_dataclass_is_immutable() -> None:
    c = CombinedConfidence(value=0.5, sources=["rule"], method=METHOD_WEIGHTED_MEAN)
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.value = 1.0  # type: ignore[misc]
