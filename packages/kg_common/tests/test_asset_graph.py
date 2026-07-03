"""Asset dependency graph + topological order tests (§9.4)."""

from __future__ import annotations

import pytest

from kg_common.asset_graph import Asset, AssetGraph, CycleError


def _linear_chain() -> AssetGraph:
    # a -> b -> c -> d  (each depends on the previous one).
    g = AssetGraph()
    g.add_asset("a")
    g.add_asset("b", ["a"])
    g.add_asset("c", ["b"])
    g.add_asset("d", ["c"])
    return g


def _diamond() -> AssetGraph:
    #      a
    #     / \
    #    b   c
    #     \ /
    #      d
    g = AssetGraph()
    g.add_asset("a")
    g.add_asset("b", ["a"])
    g.add_asset("c", ["a"])
    g.add_asset("d", ["b", "c"])
    return g


def test_asset_as_dict_and_dedup() -> None:
    g = AssetGraph()
    asset = g.add_asset("d", ["b", "a", "b"])
    assert isinstance(asset, Asset)
    # deps de-duplicated in first-seen order, JSON view uses a plain list.
    assert asset.deps == ("b", "a")
    assert asset.as_dict() == {"key": "d", "deps": ["b", "a"]}
    assert isinstance(asset.as_dict()["deps"], list)


def test_linear_chain_topo_order() -> None:
    # Only one valid order exists for a strict chain.
    assert _linear_chain().topo_order() == ["a", "b", "c", "d"]


def test_diamond_topo_order_a_before_bc_before_d() -> None:
    order = _diamond().topo_order()
    pos = {k: i for i, k in enumerate(order)}
    # a precedes both branches; both branches precede the join d.
    assert pos["a"] < pos["b"]
    assert pos["a"] < pos["c"]
    assert pos["b"] < pos["d"]
    assert pos["c"] < pos["d"]
    # Deterministic tie-break: b sorts before c.
    assert order == ["a", "b", "c", "d"]


def test_cycle_raises_cycle_error() -> None:
    g = AssetGraph()
    g.add_asset("x", ["z"])
    g.add_asset("y", ["x"])
    g.add_asset("z", ["y"])  # x -> y -> z -> x
    with pytest.raises(CycleError) as excinfo:
        g.topo_order()
    # The whole tangle is reported, sorted, for diagnostics.
    assert excinfo.value.nodes == ("x", "y", "z")


def test_downstream_of_is_transitive() -> None:
    g = _linear_chain()
    # a feeds b feeds c feeds d — so everything downstream of a is b, c, d.
    assert g.downstream_of("a") == ["b", "c", "d"]
    assert g.downstream_of("c") == ["d"]
    assert g.downstream_of("d") == []  # leaf has no dependents


def test_downstream_of_diamond_transitive() -> None:
    g = _diamond()
    # a reaches both branches and the join, sorted and self-excluded.
    assert g.downstream_of("a") == ["b", "c", "d"]
    assert g.downstream_of("b") == ["d"]


def test_upstream_of_is_transitive() -> None:
    g = _linear_chain()
    # d depends transitively on c, b and a.
    assert g.upstream_of("d") == ["a", "b", "c"]
    assert g.upstream_of("b") == ["a"]
    assert g.upstream_of("a") == []  # root has no dependencies


def test_upstream_of_diamond_transitive() -> None:
    g = _diamond()
    # d joins both branches, which both trace back to a.
    assert g.upstream_of("d") == ["a", "b", "c"]
    assert g.upstream_of("c") == ["a"]


def test_roots_and_leaves() -> None:
    g = _diamond()
    assert g.roots() == ["a"]  # only a has no upstream
    assert g.leaves() == ["d"]  # only d has no dependents
    # A disconnected extra asset is both a root and a leaf.
    g.add_asset("solo")
    assert g.roots() == ["a", "solo"]
    assert g.leaves() == ["d", "solo"]


def test_unknown_key_returns_empty() -> None:
    g = _linear_chain()
    assert g.upstream_of("missing") == []
    assert g.downstream_of("missing") == []
    assert g.get_asset("missing") is None
    assert "missing" not in g


def test_external_deps_are_ignored() -> None:
    # "raw" is never registered, so it is treated as an external input.
    g = AssetGraph()
    g.add_asset("clean", ["raw"])
    g.add_asset("report", ["clean"])
    assert g.topo_order() == ["clean", "report"]
    # clean has no *registered* upstream, so it is a root despite the external dep.
    assert g.roots() == ["clean"]
    assert g.upstream_of("clean") == []
    assert g.upstream_of("report") == ["clean"]


def test_topo_order_deterministic_on_ties() -> None:
    # Insertion order deliberately clashes with sorted order; the result must
    # still be sorted among independent (tie) assets, not insertion-ordered.
    g = AssetGraph()
    for key in ("m", "b", "z", "a", "q"):
        g.add_asset(key)  # five independent roots, no deps between them
    assert g.topo_order() == ["a", "b", "m", "q", "z"]
    # Same tie-break holds within a rank: shared root, three independent children.
    g2 = AssetGraph()
    g2.add_asset("root")
    for key in ("y", "x", "w"):
        g2.add_asset(key, ["root"])
    assert g2.topo_order() == ["root", "w", "x", "y"]


def test_duplicate_registration_raises() -> None:
    g = AssetGraph()
    g.add_asset("a")
    with pytest.raises(ValueError, match="already registered"):
        g.add_asset("a", ["b"])
