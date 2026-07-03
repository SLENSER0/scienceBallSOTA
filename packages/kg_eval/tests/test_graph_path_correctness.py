"""Тесты корректности путей графа — hand-checkable path checks (§18.7)."""

from __future__ import annotations

from kg_eval.graph_path_correctness import PathCheckResult, check_path

SPINE = ["Material", "ProcessingRegime", "Measurement", "Evidence"]
EDGES = ["HAS_REGIME", "MEASURED", "SUPPORTED_BY"]


def test_exact_spine_order_ok() -> None:
    res = check_path(SPINE, SPINE)
    assert res.node_order_ok is True
    assert res.ok is True
    assert res.missing_labels == ()
    assert res.present_labels == tuple(SPINE)


def test_reversed_path_order_not_ok() -> None:
    res = check_path(list(reversed(SPINE)), SPINE)
    assert res.node_order_ok is False
    assert res.ok is False


def test_extra_intermediate_nodes_ok() -> None:
    path = ["Material", "Sample", "ProcessingRegime", "Instrument", "Measurement", "Evidence"]
    res = check_path(path, SPINE)
    assert res.node_order_ok is True
    assert res.ok is True
    assert res.missing_labels == ()


def test_missing_evidence() -> None:
    path = ["Material", "ProcessingRegime", "Measurement"]
    res = check_path(path, SPINE)
    assert res.missing_labels == ("Evidence",)
    assert res.node_order_ok is False
    assert res.ok is False


def test_edge_types_ok() -> None:
    res = check_path(SPINE, SPINE, edge_types=EDGES, required_edges=EDGES)
    assert res.edge_types_ok is True
    assert res.ok is True


def test_wrong_edge_order_not_ok() -> None:
    wrong = ["MEASURED", "HAS_REGIME", "SUPPORTED_BY"]
    res = check_path(SPINE, SPINE, edge_types=wrong, required_edges=EDGES)
    assert res.edge_types_ok is False
    assert res.ok is False


def test_required_edges_none_is_ok() -> None:
    res = check_path(SPINE, SPINE, edge_types=["ANYTHING"], required_edges=None)
    assert res.edge_types_ok is True
    assert res.ok is True


def test_as_dict_ok_is_bool() -> None:
    res = check_path(SPINE, SPINE)
    d = res.as_dict()
    assert isinstance(d["ok"], bool)
    assert d["ok"] is True
    assert isinstance(res, PathCheckResult)
    assert d["missing_labels"] == []
