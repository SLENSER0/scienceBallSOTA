"""Tests for entity-neighbor / graph-expand parameter parsing (§14.5/§14.6).

Проверяем зажим глубины, CSV-разбор с дедупликацией и структурный вид.
Verify depth clamping, CSV parsing with dedupe and the wire form.
"""

from __future__ import annotations

from api_gateway.neighbor_params import (
    DEFAULT_DEPTH,
    MAX_DEPTH,
    NeighborParams,
    clamp_depth,
    parse_neighbor_params,
)


def test_constants() -> None:
    assert DEFAULT_DEPTH == 1
    assert MAX_DEPTH == 3


def test_clamp_depth_none_defaults() -> None:
    assert clamp_depth(None) == 1


def test_clamp_depth_below_min() -> None:
    assert clamp_depth(0) == 1


def test_clamp_depth_negative() -> None:
    assert clamp_depth(-4) == 1


def test_clamp_depth_above_max() -> None:
    assert clamp_depth(5) == 3


def test_clamp_depth_in_range() -> None:
    assert clamp_depth(2) == 2


def test_clamp_depth_boundaries() -> None:
    assert clamp_depth(1) == 1
    assert clamp_depth(3) == 3


def test_parse_depth_and_types() -> None:
    params = parse_neighbor_params({"depth": "2", "types": "Material,Property"})
    assert params.depth == 2
    assert params.node_types == ("Material", "Property")


def test_parse_depth_clamped_high() -> None:
    assert parse_neighbor_params({"depth": "9"}).depth == 3


def test_parse_empty_mapping() -> None:
    params = parse_neighbor_params({})
    assert params.depth == 1
    assert params.node_types == ()
    assert params.node_ids == ()
    assert params.edge_types == ()


def test_parse_types_deduped_order_preserved() -> None:
    assert parse_neighbor_params({"types": "A,A,B"}).node_types == ("A", "B")


def test_parse_node_ids() -> None:
    assert parse_neighbor_params({"node_ids": "n1,n2"}).node_ids == ("n1", "n2")


def test_parse_edge_types() -> None:
    params = parse_neighbor_params({"edge_types": "HAS,HAS,USES"})
    assert params.edge_types == ("HAS", "USES")


def test_parse_empty_tokens_dropped() -> None:
    params = parse_neighbor_params({"node_ids": " n1 , , n2 ,"})
    assert params.node_ids == ("n1", "n2")


def test_parse_depth_missing_defaults() -> None:
    assert parse_neighbor_params({"types": "X"}).depth == DEFAULT_DEPTH


def test_parse_depth_blank_string_defaults() -> None:
    assert parse_neighbor_params({"depth": "  "}).depth == 1


def test_parse_depth_non_numeric_defaults() -> None:
    assert parse_neighbor_params({"depth": "abc"}).depth == 1


def test_parse_depth_int_value() -> None:
    assert parse_neighbor_params({"depth": 2}).depth == 2


def test_as_dict_empty() -> None:
    assert parse_neighbor_params({}).as_dict()["depth"] == 1


def test_as_dict_full_shape() -> None:
    params = parse_neighbor_params(
        {"node_ids": "n1,n2", "depth": "2", "types": "Material", "edge_types": "HAS"}
    )
    assert params.as_dict() == {
        "node_ids": ["n1", "n2"],
        "depth": 2,
        "node_types": ["Material"],
        "edge_types": ["HAS"],
    }


def test_params_frozen() -> None:
    params = NeighborParams(node_ids=(), depth=1, node_types=(), edge_types=())
    try:
        params.depth = 2  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("NeighborParams should be immutable")
