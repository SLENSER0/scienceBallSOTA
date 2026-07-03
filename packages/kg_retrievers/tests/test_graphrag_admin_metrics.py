"""Tests for GraphRAG admin metrics (§11.13)."""

from __future__ import annotations

from kg_retrievers.graphrag_admin_metrics import (
    GraphRagAdminMetrics,
    build_admin_metrics,
)


def test_no_active_build_zeroes_version_and_communities() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[],
        cache_stats={"hits": 0, "misses": 0},
    )
    assert m.build_version is None
    assert m.n_communities == 0
    assert m.last_rebuild_at is None


def test_avg_latency_is_arithmetic_mean() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[100.0, 200.0, 300.0],
        cache_stats={"hits": 0, "misses": 0},
    )
    assert m.avg_global_latency_ms == 200.0


def test_empty_latencies_yield_zero_avg() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[],
        cache_stats={"hits": 1, "misses": 1},
    )
    assert m.avg_global_latency_ms == 0.0


def test_cache_hit_rate_and_n_searches() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[],
        cache_stats={"hits": 3, "misses": 1},
    )
    assert m.cache_hit_rate == 0.75
    assert m.n_searches == 4


def test_empty_cache_hit_rate_is_zero_without_error() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[],
        cache_stats={"hits": 0, "misses": 0},
    )
    assert m.cache_hit_rate == 0.0
    assert m.n_searches == 0


def test_active_build_echoes_created_at_and_fields() -> None:
    m = build_admin_metrics(
        active_build={
            "build_version": "gr-2026-07-03",
            "n_communities": 42,
            "created_at": "2026-07-03T10:00:00Z",
        },
        latencies_ms=[50.0],
        cache_stats={"hits": 2, "misses": 2},
    )
    assert m.build_version == "gr-2026-07-03"
    assert m.n_communities == 42
    assert m.last_rebuild_at == "2026-07-03T10:00:00Z"
    assert m.cache_hit_rate == 0.5
    assert m.n_searches == 4


def test_as_dict_avg_latency_is_float() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[100.0, 200.0, 300.0],
        cache_stats={"hits": 3, "misses": 1},
    )
    d = m.as_dict()
    assert isinstance(d["avg_global_latency_ms"], float)
    assert d["avg_global_latency_ms"] == 200.0
    assert d["cache_hit_rate"] == 0.75
    assert d["n_searches"] == 4


def test_metrics_is_frozen() -> None:
    m = build_admin_metrics(
        active_build=None,
        latencies_ms=[],
        cache_stats={"hits": 0, "misses": 0},
    )
    assert isinstance(m, GraphRagAdminMetrics)
    try:
        m.n_searches = 99  # type: ignore[misc]
    except Exception as exc:  # frozen dataclass raises FrozenInstanceError
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("expected frozen dataclass to reject mutation")
