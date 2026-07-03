"""Tests for temperature-scaled softmax normalizer (§12.4)."""

from __future__ import annotations

import math

import pytest

from kg_retrievers.softmax_scores import (
    SoftmaxResult,
    softmax_normalize,
    to_distribution,
)


def test_probs_sum_to_one() -> None:
    probs = softmax_normalize({"a": 1.0, "b": 2.0, "c": 3.0})
    assert math.isclose(math.fsum(probs.values()), 1.0, abs_tol=1e-9)


def test_equal_scores_are_uniform() -> None:
    probs = softmax_normalize({"a": 2.0, "b": 2.0})
    assert math.isclose(probs["a"], 0.5, abs_tol=1e-9)
    assert math.isclose(probs["b"], 0.5, abs_tol=1e-9)


def test_strictly_larger_score_gets_strictly_larger_prob() -> None:
    probs = softmax_normalize({"a": 1.0, "b": 2.0})
    assert probs["b"] > probs["a"]


def test_large_temperature_drives_toward_uniform() -> None:
    scores = {"a": 0.0, "b": 4.0}
    base = softmax_normalize(scores, temperature=1.0)
    hot = softmax_normalize(scores, temperature=1000.0)
    base_gap = abs(base["a"] - base["b"])
    hot_gap = abs(hot["a"] - hot["b"])
    assert hot_gap < base_gap
    assert math.isclose(hot["a"], 0.5, abs_tol=1e-2)


def test_small_temperature_peaks_on_max() -> None:
    probs = softmax_normalize({"a": 0.0, "b": 4.0}, temperature=0.01)
    assert math.isclose(probs["b"], 1.0, abs_tol=1e-9)
    assert math.isclose(probs["a"], 0.0, abs_tol=1e-9)


def test_huge_scores_do_not_overflow() -> None:
    probs = softmax_normalize({"a": 1000.0, "b": 1001.0})
    assert all(math.isfinite(p) for p in probs.values())
    assert math.isclose(math.fsum(probs.values()), 1.0, abs_tol=1e-9)
    assert probs["b"] > probs["a"]


def test_single_element() -> None:
    result = to_distribution({"only": 7.0})
    assert math.isclose(result.probs["only"], 1.0, abs_tol=1e-9)
    assert math.isclose(result.entropy, 0.0, abs_tol=1e-9)


def test_entropy_of_uniform_n2_is_ln2() -> None:
    result = to_distribution({"a": 5.0, "b": 5.0})
    assert math.isclose(result.entropy, math.log(2), abs_tol=1e-9)


def test_empty_input() -> None:
    assert softmax_normalize({}) == {}
    result = to_distribution({})
    assert result.probs == {}
    assert result.entropy == 0.0


def test_result_as_dict_roundtrip() -> None:
    result = to_distribution({"a": 1.0, "b": 2.0}, temperature=2.0)
    payload = result.as_dict()
    assert payload["temperature"] == 2.0
    assert math.isclose(math.fsum(payload["probs"].values()), 1.0, abs_tol=1e-9)
    assert payload["entropy"] == result.entropy
    # Returned dict is a copy, not the internal mapping.
    payload["probs"]["a"] = -1.0
    assert result.probs["a"] != -1.0


def test_frozen_dataclass_is_immutable() -> None:
    result = SoftmaxResult(temperature=1.0, probs={"a": 1.0}, entropy=0.0)
    with pytest.raises((AttributeError, TypeError)):
        result.temperature = 2.0  # type: ignore[misc]


def test_non_positive_temperature_rejected() -> None:
    with pytest.raises(ValueError):
        softmax_normalize({"a": 1.0}, temperature=0.0)
    with pytest.raises(ValueError):
        softmax_normalize({"a": 1.0}, temperature=-1.0)


def test_entropy_matches_manual_computation() -> None:
    scores = {"a": 1.0, "b": 2.0, "c": 3.0}
    result = to_distribution(scores)
    expected = -math.fsum(p * math.log(p) for p in result.probs.values())
    assert math.isclose(result.entropy, expected, abs_tol=1e-12)
    # Entropy is bounded by ln(n) for n outcomes.
    assert result.entropy <= math.log(3) + 1e-12
