"""Tests for per-source score normalization (§12.3 Mode B)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.score_normalization import (
    NormalizationResult,
    minmax_normalize,
    normalize_per_source,
    zscore_normalize,
)


def test_minmax_basic() -> None:
    out = minmax_normalize({"a": 10, "b": 0, "c": 5})
    assert out["a"] == 1.0
    assert out["b"] == 0.0
    assert out["c"] == 0.5


def test_minmax_constant_input_all_zero() -> None:
    # All-equal input must avoid div-by-zero and map to a neutral 0.0.
    assert minmax_normalize({"x": 7, "y": 7}) == {"x": 0.0, "y": 0.0}


def test_minmax_negative_values() -> None:
    # Minimum (most negative) maps to 0.0, maximum to 1.0.
    out = minmax_normalize({"a": -10, "b": -5, "c": 0})
    assert out["a"] == 0.0
    assert out["c"] == 1.0
    assert out["b"] == 0.5


def test_minmax_empty() -> None:
    assert minmax_normalize({}) == {}


def test_zscore_mean_zero_and_middle() -> None:
    out = zscore_normalize({"a": 1, "b": 2, "c": 3})
    # Standardized outputs have mean 0; the central value equals the mean → 0.0.
    assert abs(sum(out.values()) / len(out)) < 1e-9
    assert abs(out["b"]) < 1e-9
    assert out["a"] < 0.0 < out["c"]


def test_zscore_zero_variance_all_zero() -> None:
    assert zscore_normalize({"a": 4, "b": 4, "c": 4}) == {"a": 0.0, "b": 0.0, "c": 0.0}


def test_zscore_unit_std() -> None:
    # Population std of {1,2,3} is sqrt(2/3); check c maps to (3-2)/std.
    out = zscore_normalize({"a": 1, "b": 2, "c": 3})
    expected = 1.0 / (2.0 / 3.0) ** 0.5
    assert abs(out["c"] - expected) < 1e-9
    assert abs(out["a"] + expected) < 1e-9


def test_zscore_empty() -> None:
    assert zscore_normalize({}) == {}


def test_normalize_per_source_independent() -> None:
    by_source = {
        "dense": {"a": 100, "b": 0},  # own max 100 → 1.0
        "keyword": {"a": 2, "b": 4},  # own max 4 → 1.0
    }
    out = normalize_per_source(by_source, method="minmax")
    assert out["dense"]["a"] == 1.0
    assert out["dense"]["b"] == 0.0
    # keyword normalized on its own scale, independent of dense.
    assert out["keyword"]["b"] == 1.0
    assert out["keyword"]["a"] == 0.0


def test_normalize_per_source_zscore() -> None:
    by_source = {"s1": {"a": 1, "b": 2, "c": 3}}
    out = normalize_per_source(by_source, method="zscore")
    assert abs(out["s1"]["b"]) < 1e-9


def test_normalize_per_source_default_is_minmax() -> None:
    out = normalize_per_source({"s": {"a": 0, "b": 10}})
    assert out["s"]["b"] == 1.0


def test_unknown_method_raises() -> None:
    with pytest.raises(ValueError):
        normalize_per_source({"s": {"a": 1.0}}, method="softmax")


def test_result_as_dict() -> None:
    res = NormalizationResult(method="minmax", scores={"a": 1.0, "b": 0.0})
    d = res.as_dict()
    assert set(d) == {"method", "scores"}
    assert d["method"] == "minmax"
    assert d["scores"] == {"a": 1.0, "b": 0.0}


def test_result_is_frozen() -> None:
    res = NormalizationResult(method="zscore", scores={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.method = "minmax"  # type: ignore[misc]
