"""Hand-checked tests for the §12.16 fusion-weights config object.

Каждое ожидаемое значение задано конкретным числом/строкой по §12.16/§12.4/§10.2.
"""

from __future__ import annotations

import pytest

from kg_retrievers.fusion import DEFAULT_FUSION_WEIGHTS, DEFAULT_RRF_K
from kg_retrievers.fusion_config import (
    FUSION_METHODS,
    METHOD_RRF,
    METHOD_WEIGHTED,
    FusionConfig,
    default_fusion_config,
)

# ---------------------------------------------------------------------------
# Defaults (§12.16)
# ---------------------------------------------------------------------------


def test_default_fusion_config_is_valid() -> None:
    """default_fusion_config() → weighted / §10.2 weights / rrf_k 60 (no raise)."""
    cfg = default_fusion_config()
    assert cfg.method == METHOD_WEIGHTED == "weighted"
    assert cfg.weights == {
        "dense": 0.35,
        "sparse": 0.25,
        "bm25": 0.20,
        "graph_proximity": 0.10,
        "evidence_quality": 0.10,
    }
    assert cfg.weights == DEFAULT_FUSION_WEIGHTS
    assert sum(cfg.weights.values()) == pytest.approx(1.0, abs=1e-9)


def test_rrf_k_default_is_sixty() -> None:
    """Default rrf_k == DEFAULT_RRF_K == 60 (§12.4)."""
    assert DEFAULT_RRF_K == 60
    assert FusionConfig().rrf_k == 60
    assert default_fusion_config().rrf_k == 60


def test_known_method_constants() -> None:
    """The two §12.4 methods are exactly {'rrf', 'weighted'}."""
    assert METHOD_RRF == "rrf"
    assert METHOD_WEIGHTED == "weighted"
    assert sorted(FUSION_METHODS) == ["rrf", "weighted"]


# ---------------------------------------------------------------------------
# weighted method → §12.4 «sum == 1.0» invariant
# ---------------------------------------------------------------------------


def test_weighted_with_bad_sum_raises() -> None:
    """weighted weights summing to 0.9 violate §12.4 → ValueError."""
    bad = {
        "dense": 0.35,
        "sparse": 0.25,
        "bm25": 0.20,
        "graph_proximity": 0.10,
        "evidence_quality": 0.0,
    }
    assert sum(bad.values()) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        FusionConfig(method="weighted", weights=bad)


def test_weighted_with_good_sum_ok() -> None:
    """weighted weights summing to exactly 1.0 are accepted and stored verbatim."""
    good = {"dense": 0.5, "sparse": 0.5}
    cfg = FusionConfig(method="weighted", weights=good, rrf_k=60)
    assert cfg.method == "weighted"
    assert cfg.weights == {"dense": 0.5, "sparse": 0.5}


# ---------------------------------------------------------------------------
# rrf method → weights NOT constrained (not used in the RRF formula)
# ---------------------------------------------------------------------------


def test_rrf_method_ok_ignores_weight_sum() -> None:
    """rrf accepts weights whose sum != 1.0 (they are unused by §7.5 RRF)."""
    weights = {"dense": 0.7, "bm25": 0.5}  # sum 1.2 — illegal for weighted
    cfg = FusionConfig(method="rrf", weights=weights, rrf_k=30)
    assert cfg.method == METHOD_RRF == "rrf"
    assert cfg.rrf_k == 30
    assert cfg.weights == {"dense": 0.7, "bm25": 0.5}
    assert sum(cfg.weights.values()) == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# method validation
# ---------------------------------------------------------------------------


def test_unknown_method_raises() -> None:
    """An unknown method string is rejected (§12.4 flag is a closed set)."""
    with pytest.raises(ValueError):
        FusionConfig(method="magic")


def test_nonpositive_rrf_k_raises() -> None:
    """rrf_k must be > 0 (1/(k+rank) requires k>0)."""
    with pytest.raises(ValueError):
        FusionConfig(method="rrf", rrf_k=0)


# ---------------------------------------------------------------------------
# as_dict / from_dict
# ---------------------------------------------------------------------------


def test_as_dict_shape() -> None:
    """as_dict() exposes method/weights/rrf_k as concrete plain values."""
    cfg = FusionConfig(method="weighted", weights={"dense": 0.6, "bm25": 0.4}, rrf_k=45)
    assert cfg.as_dict() == {
        "method": "weighted",
        "weights": {"dense": 0.6, "bm25": 0.4},
        "rrf_k": 45,
    }


def test_from_dict_builds_expected_config() -> None:
    """from_dict() maps a plain dict to a validated config with concrete values."""
    cfg = FusionConfig.from_dict(
        {"method": "rrf", "weights": {"dense": 0.9, "bm25": 0.9}, "rrf_k": 10}
    )
    assert cfg.method == "rrf"
    assert cfg.weights == {"dense": 0.9, "bm25": 0.9}
    assert cfg.rrf_k == 10


def test_from_dict_defaults_on_missing_keys() -> None:
    """from_dict({}) falls back to weighted / §10.2 weights / rrf_k 60."""
    cfg = FusionConfig.from_dict({})
    assert cfg.method == "weighted"
    assert cfg.weights == DEFAULT_FUSION_WEIGHTS
    assert cfg.rrf_k == 60


def test_as_dict_from_dict_roundtrip() -> None:
    """from_dict(as_dict(cfg)) == cfg (frozen dataclass value equality)."""
    cfg = FusionConfig(method="weighted", weights={"dense": 0.3, "bm25": 0.7}, rrf_k=25)
    assert FusionConfig.from_dict(cfg.as_dict()) == cfg
    # Default config round-trips too.
    d = default_fusion_config()
    assert FusionConfig.from_dict(d.as_dict()) == d


def test_from_dict_revalidates_bad_sum() -> None:
    """from_dict re-runs validation: weighted with a bad sum raises ValueError."""
    with pytest.raises(ValueError):
        FusionConfig.from_dict({"method": "weighted", "weights": {"dense": 0.2, "bm25": 0.2}})


# ---------------------------------------------------------------------------
# immutability / defensive copy (house style: frozen dataclass owns its data)
# ---------------------------------------------------------------------------


def test_frozen_and_defensive_copy() -> None:
    """Config is frozen and owns a private copy of the input weights dict."""
    src = {"dense": 0.4, "bm25": 0.6}
    cfg = FusionConfig(method="weighted", weights=src)
    src["dense"] = 999.0  # mutate caller's dict → config unaffected
    assert cfg.weights == {"dense": 0.4, "bm25": 0.6}
    with pytest.raises(Exception):  # noqa: B017 - frozen assignment must fail
        cfg.method = "rrf"  # type: ignore[misc]
    # as_dict returns a fresh copy — mutating it does not touch the config.
    out = cfg.as_dict()
    out["weights"]["dense"] = 0.0
    assert cfg.weights["dense"] == 0.4
