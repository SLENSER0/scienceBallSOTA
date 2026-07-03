"""Tests for the graph-endpoint truncation guard (§14.6).

Проверяем детерминированное усечение: сохранение первых узлов, отбрасывание
висячих рёбер, ограничение числа рёбер и флаг ``truncated``.

Deterministic truncation: keep-first nodes, dangling-edge drop, edge cap and
the ``truncated`` flag / ``dropped_*`` counters.
"""

from __future__ import annotations

from api_gateway.graph_response_limit import LimitResult, apply_limits

NODES = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
CHAIN = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]


def test_node_cap_drops_dangling_edge() -> None:
    """max_nodes=2 keeps ('a','b'), drops the b->c edge as dangling."""
    result = apply_limits(NODES, CHAIN, max_nodes=2, max_edges=10)
    assert tuple(n["id"] for n in result.nodes) == ("a", "b")
    assert len(result.nodes) == 2
    assert len(result.edges) == 1
    assert result.dropped_nodes == 1
    assert result.dropped_edges == 1
    assert result.truncated is True


def test_generous_limits_keep_everything() -> None:
    """max_nodes/max_edges above the graph size drop nothing."""
    result = apply_limits(NODES, CHAIN, max_nodes=10, max_edges=10)
    assert result.truncated is False
    assert result.dropped_nodes == 0
    assert result.dropped_edges == 0
    assert len(result.nodes) == 3
    assert len(result.edges) == 2


def test_edge_cap_among_kept_nodes() -> None:
    """Three edges among kept nodes, max_edges=1 keeps one, drops two."""
    edges = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "c"},
        {"source": "a", "target": "c"},
    ]
    result = apply_limits(NODES, edges, max_nodes=10, max_edges=1)
    assert len(result.edges) == 1
    assert result.dropped_edges == 2
    assert result.truncated is True
    # First-by-order edge is the one retained.
    assert result.edges[0] == {"source": "a", "target": "b"}


def test_empty_graph() -> None:
    """Empty input yields empty tuples and no truncation."""
    result = apply_limits([], [], max_nodes=5, max_edges=5)
    assert result.nodes == ()
    assert result.edges == ()
    assert result.truncated is False
    assert result.dropped_nodes == 0
    assert result.dropped_edges == 0


def test_zero_max_nodes_drops_all_edges() -> None:
    """max_nodes=0 keeps no nodes, so every edge is dangling and dropped."""
    result = apply_limits(NODES, CHAIN, max_nodes=0, max_edges=10)
    assert result.nodes == ()
    assert result.edges == ()
    assert result.dropped_nodes == 3
    assert result.dropped_edges == 2
    assert result.truncated is True


def test_as_dict_unlimited_case() -> None:
    """as_dict() exposes truncated=False for the unlimited case."""
    result = apply_limits(NODES, CHAIN, max_nodes=10, max_edges=10)
    payload = result.as_dict()
    assert payload["truncated"] is False
    assert payload["dropped_nodes"] == 0
    assert payload["dropped_edges"] == 0
    assert payload["nodes"] == list(NODES)
    assert payload["edges"] == list(CHAIN)


def test_result_is_frozen() -> None:
    """LimitResult is a frozen dataclass carrying immutable tuples."""
    result = apply_limits(NODES, CHAIN, max_nodes=2, max_edges=10)
    assert isinstance(result, LimitResult)
    assert isinstance(result.nodes, tuple)
    assert isinstance(result.edges, tuple)
