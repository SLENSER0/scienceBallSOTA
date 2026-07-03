"""Composite importance ensemble tests (§3.14 / §17).

Hand-checkable star graph over a fresh temp Kuzu store: a hub ``h`` wired to
three leaves ``l1, l2, l3``. On a star the hub is the unique top of *every*
centrality (degree, closeness, betweenness, PageRank), so after each metric is
min-max normalised the hub sits at ``1.0`` in all of them → composite ``1.0``:

- ``centrality_ensemble(store)[0].entity_id == 'h'``;
- every composite lies in ``[0, 1]`` and ``h.composite == 1.0``;
- a leaf's composite is strictly below the hub's;
- ``components`` holds exactly the requested metric keys;
- ``metrics=('degree',)`` uses degree alone;
- an empty store returns ``[]``;
- ordering is deterministic across repeated calls.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_centrality_ensemble import (
    DEFAULT_METRICS,
    EnsembleScore,
    centrality_ensemble,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    # 'Material' is in ENTITY_LABELS, so the node enters the projection.
    store.upsert_node(nid, "Material", name=nid)


def _star_store() -> KuzuGraphStore:
    """Hub h connected to leaves l1, l2, l3 — a classic star."""
    store = _store()
    for nid in ("h", "l1", "l2", "l3"):
        _node(store, nid)
    for leaf in ("l1", "l2", "l3"):
        store.upsert_edge("h", leaf, "RELATED_TO")
    return store


def test_hub_ranks_first() -> None:
    scores = centrality_ensemble(_star_store())
    assert scores[0].entity_id == "h"


def test_every_composite_in_unit_interval() -> None:
    for s in centrality_ensemble(_star_store()):
        assert 0.0 <= s.composite <= 1.0


def test_hub_composite_is_one() -> None:
    scores = centrality_ensemble(_star_store())
    hub = next(s for s in scores if s.entity_id == "h")
    assert hub.composite == pytest.approx(1.0)


def test_leaf_composite_below_hub() -> None:
    scores = centrality_ensemble(_star_store())
    hub = next(s for s in scores if s.entity_id == "h")
    leaf = next(s for s in scores if s.entity_id == "l1")
    assert leaf.composite < hub.composite


def test_hub_components_all_normalised_to_one() -> None:
    scores = centrality_ensemble(_star_store())
    hub = next(s for s in scores if s.entity_id == "h")
    # hub tops every metric -> each normalised component is 1.0
    for name in DEFAULT_METRICS:
        assert hub.components[name] == pytest.approx(1.0)


def test_components_hold_exactly_requested_keys() -> None:
    scores = centrality_ensemble(_star_store())
    for s in scores:
        assert set(s.components) == set(DEFAULT_METRICS)


def test_single_metric_uses_only_that_metric() -> None:
    scores = centrality_ensemble(_star_store(), metrics=("degree",))
    for s in scores:
        assert set(s.components) == {"degree"}
        assert s.composite == pytest.approx(s.components["degree"])
    assert scores[0].entity_id == "h"


def test_empty_store_returns_empty() -> None:
    assert centrality_ensemble(_store()) == []


def test_top_limits_result_length() -> None:
    scores = centrality_ensemble(_star_store(), top=2)
    assert len(scores) == 2
    assert scores[0].entity_id == "h"


def test_deterministic_and_tie_break_by_id() -> None:
    store = _star_store()
    first = centrality_ensemble(store)
    second = centrality_ensemble(store)
    assert [s.as_dict() for s in first] == [s.as_dict() for s in second]
    # the three leaves are symmetric -> equal composite, ordered by id
    leaves = [s for s in first if s.entity_id != "h"]
    assert [s.entity_id for s in leaves] == ["l1", "l2", "l3"]
    assert leaves[0].composite == pytest.approx(leaves[2].composite)


def test_score_dataclass_shape() -> None:
    s = EnsembleScore("h", 1.0, {"degree": 1.0})
    assert s.as_dict() == {
        "entity_id": "h",
        "composite": 1.0,
        "components": {"degree": 1.0},
    }
