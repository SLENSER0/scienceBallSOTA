"""Tests for the §4.9 cross-encoder reranker config.

Every expected value is hand-checked against the module defaults:
``DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"``,
``DEFAULT_TOP_N = 50``, ``DEFAULT_ENABLED = True`` and ``DEFAULT_BATCH_SIZE = 32``.
"""

from __future__ import annotations

import pytest

from kg_retrievers.reranker_config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_ENABLED,
    DEFAULT_RERANKER_MODEL,
    DEFAULT_TOP_N,
    RerankerConfig,
    default_reranker_config,
    is_permissive_model,
)


def test_defaults_match_spec() -> None:
    # §10.2 defaults: ms-marco-MiniLM cross-encoder, rerank_top_n=50, enabled, batch 32.
    cfg = default_reranker_config()
    assert cfg.model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert cfg.top_n == 50
    assert cfg.enabled is True
    assert cfg.batch_size == 32
    # A bare RerankerConfig() takes the same module defaults.
    assert cfg == RerankerConfig()
    assert (DEFAULT_RERANKER_MODEL, DEFAULT_TOP_N, DEFAULT_ENABLED, DEFAULT_BATCH_SIZE) == (
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        50,
        True,
        32,
    )


def test_batch_size_default() -> None:
    # Omitting batch_size falls back to 32; overriding it is honoured.
    assert RerankerConfig().batch_size == 32
    assert RerankerConfig(batch_size=8).batch_size == 8


def test_from_dict_override() -> None:
    # Every field overridden — none should keep its default.
    cfg = RerankerConfig.from_dict(
        {"model": "BAAI/bge-reranker-base", "top_n": 10, "enabled": False, "batch_size": 4}
    )
    assert cfg.model == "BAAI/bge-reranker-base"
    assert cfg.top_n == 10
    assert cfg.enabled is False
    assert cfg.batch_size == 4


def test_from_dict_partial_fills_defaults() -> None:
    # A partial dict keeps defaults for the untouched fields (only enabled is set).
    cfg = RerankerConfig.from_dict({"enabled": False})
    assert cfg.enabled is False
    assert cfg.model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert cfg.top_n == 50
    assert cfg.batch_size == 32
    # An empty dict reproduces the full default config.
    assert RerankerConfig.from_dict({}) == default_reranker_config()


def test_top_n_below_one_raises() -> None:
    with pytest.raises(ValueError, match="top_n must be >= 1"):
        RerankerConfig(top_n=0)
    with pytest.raises(ValueError, match="top_n must be >= 1"):
        RerankerConfig(top_n=-3)
    # top_n == 1 is the smallest valid value and must NOT raise.
    assert RerankerConfig(top_n=1).top_n == 1


def test_batch_size_below_one_raises() -> None:
    with pytest.raises(ValueError, match="batch_size must be >= 1"):
        RerankerConfig(batch_size=0)


def test_enabled_toggle() -> None:
    # enabled flag flows through construction and as_dict unchanged.
    off = RerankerConfig(enabled=False)
    assert off.enabled is False
    assert off.as_dict()["enabled"] is False
    on = RerankerConfig(enabled=True)
    assert on.enabled is True
    assert on.as_dict()["enabled"] is True


def test_as_dict_round_trip() -> None:
    cfg = RerankerConfig(
        model="mixedbread-ai/mxbai-rerank-large-v1", top_n=25, enabled=False, batch_size=16
    )
    d = cfg.as_dict()
    assert d == {
        "model": "mixedbread-ai/mxbai-rerank-large-v1",
        "top_n": 25,
        "enabled": False,
        "batch_size": 16,
    }
    # Round-trip: from_dict(as_dict(x)) == x.
    assert RerankerConfig.from_dict(d) == cfg
    # The default config also survives a round-trip.
    default_cfg = default_reranker_config()
    assert RerankerConfig.from_dict(default_cfg.as_dict()) == default_cfg


def test_is_permissive_true_for_ms_marco_minilm() -> None:
    # The default ms-marco MiniLM cross-encoder is a permissive OSS model.
    assert is_permissive_model("cross-encoder/ms-marco-MiniLM-L-6-v2") is True
    assert is_permissive_model(DEFAULT_RERANKER_MODEL) is True
    # Matching is case-insensitive and covers the wider cross-encoder family.
    assert is_permissive_model("CROSS-ENCODER/ms-marco-MiniLM-L-12-v2") is True
    assert is_permissive_model("BAAI/bge-reranker-large") is True


def test_is_permissive_false_for_non_oss_or_empty() -> None:
    # Proprietary / non-allow-listed rerankers and empty strings are rejected.
    assert is_permissive_model("cohere/rerank-english-v3.0") is False
    assert is_permissive_model("openai/text-embedding-3-large") is False
    assert is_permissive_model("") is False


def test_frozen_is_immutable() -> None:
    cfg = default_reranker_config()
    with pytest.raises((AttributeError, TypeError)):
        cfg.top_n = 5  # type: ignore[misc]
