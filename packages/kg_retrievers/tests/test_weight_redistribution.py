"""Tests for §12.4/§12.5 fusion-weight redistribution (hand-checkable)."""

from __future__ import annotations

from kg_retrievers.weight_redistribution import (
    RedistributedWeights,
    is_normalized,
    redistribute,
)

# §12.5 Mode A default channel weights (sum == 1.0).
BASE = {
    "dense": 0.35,
    "sparse": 0.25,
    "bm25": 0.20,
    "graph_proximity": 0.10,
    "evidence_quality": 0.10,
}


def test_drop_graph_proximity_sums_to_one() -> None:
    # §12.5: Mode A lacks graph_proximity; its 0.10 is redistributed.
    available = {"dense", "sparse", "bm25", "evidence_quality"}
    res = redistribute(BASE, available)
    assert abs(sum(res.weights.values()) - 1.0) <= 1e-9
    assert is_normalized(res.weights)


def test_drop_graph_proximity_preserves_dense_sparse_ratio() -> None:
    # Proportions survive rescaling: 0.35 / 0.25 == 1.4 before and after.
    available = {"dense", "sparse", "bm25", "evidence_quality"}
    res = redistribute(BASE, available)
    assert abs(res.weights["dense"] / res.weights["sparse"] - (0.35 / 0.25)) <= 1e-9
    # Surviving total was 0.90, so dense -> 0.35/0.90.
    assert abs(res.weights["dense"] - 0.35 / 0.90) <= 1e-12


def test_dropped_tuple_reports_graph_proximity() -> None:
    available = {"dense", "sparse", "bm25", "evidence_quality"}
    res = redistribute(BASE, available)
    assert res.dropped == ("graph_proximity",)
    assert "graph_proximity" not in res.weights


def test_all_available_returns_unchanged_and_normalized() -> None:
    available = set(BASE)
    res = redistribute(BASE, available)
    assert res.dropped == ()
    assert res.weights == BASE  # already sums to 1.0, nothing to rescale
    assert is_normalized(res.weights)


def test_drop_every_key_yields_empty_and_not_normalized() -> None:
    res = redistribute(BASE, set())
    assert res.weights == {}
    assert res.dropped == tuple(sorted(BASE))
    assert is_normalized({}) is False
    assert is_normalized(res.weights) is False


def test_single_survivor_gets_weight_one() -> None:
    res = redistribute(BASE, {"dense"})
    assert res.weights == {"dense": 1.0}
    assert is_normalized(res.weights)


def test_as_dict_shape() -> None:
    res = redistribute(BASE, {"dense", "sparse"})
    d = res.as_dict()
    assert set(d) == {"weights", "dropped"}
    assert d["weights"] == res.weights
    assert d["dropped"] == res.dropped


def test_frozen_dataclass() -> None:
    res = RedistributedWeights(weights={"dense": 1.0}, dropped=())
    try:
        res.dropped = ("x",)  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("RedistributedWeights must be frozen")


def test_is_normalized_tolerance() -> None:
    assert is_normalized({"a": 0.5, "b": 0.5 + 5e-10})
    assert not is_normalized({"a": 0.5, "b": 0.6})
