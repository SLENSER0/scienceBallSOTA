"""Asset DAG validation tests (§9.4)."""

from __future__ import annotations

from kg_common.asset_graph import Asset
from kg_common.dag_validate import DagValidation, validate_dag


def test_valid_dag_is_ok() -> None:
    # Diamond: a -> {b, c} -> d. No cycles, no dangling deps.
    assets = [
        Asset("a"),
        Asset("b", ("a",)),
        Asset("c", ("a",)),
        Asset("d", ("b", "c")),
    ]
    result = validate_dag(assets)
    assert isinstance(result, DagValidation)
    assert result.ok is True
    assert result.cycles == ()
    assert result.missing_deps == ()
    assert result.roots == ("a",)
    assert result.leaves == ("d",)


def test_cycle_is_detected() -> None:
    # a depends on b and b depends on a: no topological order exists.
    assets = [Asset("a", ("b",)), Asset("b", ("a",))]
    result = validate_dag(assets)
    assert result.ok is False
    # CycleError.nodes are sorted, so both tangled keys are reported.
    assert result.cycles == ("a", "b")
    assert result.missing_deps == ()
    # Every node has a registered upstream/dependent, so no roots or leaves.
    assert result.roots == ()
    assert result.leaves == ()


def test_missing_dep_is_flagged() -> None:
    # b references "x", which is never registered → dangling edge.
    assets = [Asset("a"), Asset("b", ("x",))]
    result = validate_dag(assets)
    assert result.ok is False
    assert result.cycles == ()
    assert result.missing_deps == ("x",)
    # The dangling dep is ignored by the graph, so a and b are both roots.
    assert result.roots == ("a", "b")
    assert result.leaves == ("a", "b")


def test_roots_and_leaves_of_linear_chain() -> None:
    # a -> b -> c -> d: single root a, single leaf d.
    assets = [
        Asset("a"),
        Asset("b", ("a",)),
        Asset("c", ("b",)),
        Asset("d", ("c",)),
    ]
    result = validate_dag(assets)
    assert result.ok is True
    assert result.roots == ("a",)
    assert result.leaves == ("d",)


def test_empty_graph() -> None:
    result = validate_dag([])
    assert result.ok is True
    assert result.cycles == ()
    assert result.missing_deps == ()
    assert result.roots == ()
    assert result.leaves == ()


def test_single_asset_is_root_and_leaf() -> None:
    result = validate_dag([Asset("solo")])
    assert result.ok is True
    assert result.roots == ("solo",)
    assert result.leaves == ("solo",)
    assert result.cycles == ()
    assert result.missing_deps == ()


def test_as_dict_shape_and_list_types() -> None:
    assets = [Asset("a"), Asset("b", ("a",))]
    d = validate_dag(assets).as_dict()
    assert d == {
        "ok": True,
        "cycles": [],
        "missing_deps": [],
        "roots": ["a"],
        "leaves": ["b"],
    }
    # JSON view uses plain lists, not tuples.
    for field in ("cycles", "missing_deps", "roots", "leaves"):
        assert isinstance(d[field], list)


def test_multiple_missing_deps_are_sorted_and_unique() -> None:
    # Two assets reference the same missing key "z" plus a distinct "y".
    assets = [Asset("a", ("z",)), Asset("b", ("z", "y"))]
    result = validate_dag(assets)
    assert result.ok is False
    assert result.missing_deps == ("y", "z")
