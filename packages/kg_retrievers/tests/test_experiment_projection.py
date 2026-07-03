"""Hand-checkable tests for the §17.12 Experiment Explorer projection.

Three seeded experiments in one temp KuzuGraphStore (edges stored directed):

  exp1 (full)     : exp1 -HAS_SAMPLE-> s1 -OF_MATERIAL-> m1 -PROCESSED_BY-> pr1
                    -MEASURED_PROPERTY-> p1
  exp2 (no Sample): exp2 -OF_MATERIAL-> m2 -PROCESSED_BY-> pr2 -MEASURED_PROPERTY-> p2
  exp3 (tail gap) : exp3 -HAS_SAMPLE-> s3 -OF_MATERIAL-> m3   (no regime / property)

All chain/edge/missing expectations below are hand-computed against this fixed shape.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_retrievers.experiment_projection import (
    CHAIN_ORDER,
    ExperimentProjection,
    build_experiment_projection,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _seed(s)
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    # Full chain.
    s.upsert_node("exp1", "Experiment", name="Experiment 1")
    s.upsert_node("s1", "Sample", name="Sample 1")
    s.upsert_node("m1", "Material", name="Material 1")
    s.upsert_node("pr1", "ProcessingRegime", name="Regime 1")
    s.upsert_node("p1", "Property", name="Property 1")
    s.upsert_edge("exp1", "s1", "HAS_SAMPLE")
    s.upsert_edge("s1", "m1", "OF_MATERIAL")
    s.upsert_edge("m1", "pr1", "PROCESSED_BY")
    s.upsert_edge("pr1", "p1", "MEASURED_PROPERTY")

    # Sample absent — experiment connects straight to Material.
    s.upsert_node("exp2", "Experiment", name="Experiment 2")
    s.upsert_node("m2", "Material", name="Material 2")
    s.upsert_node("pr2", "ProcessingRegime", name="Regime 2")
    s.upsert_node("p2", "Property", name="Property 2")
    s.upsert_edge("exp2", "m2", "OF_MATERIAL")
    s.upsert_edge("m2", "pr2", "PROCESSED_BY")
    s.upsert_edge("pr2", "p2", "MEASURED_PROPERTY")

    # Only a Material — no regime / property downstream.
    s.upsert_node("exp3", "Experiment", name="Experiment 3")
    s.upsert_node("s3", "Sample", name="Sample 3")
    s.upsert_node("m3", "Material", name="Material 3")
    s.upsert_edge("exp3", "s3", "HAS_SAMPLE")
    s.upsert_edge("s3", "m3", "OF_MATERIAL")


def test_chain_order_constant() -> None:
    assert CHAIN_ORDER == ("Experiment", "Sample", "Material", "ProcessingRegime", "Property")


def test_absent_experiment_returns_none(store: KuzuGraphStore) -> None:
    assert build_experiment_projection(store, "no_such_id") is None


def test_full_chain_five_stages_in_order(store: KuzuGraphStore) -> None:
    proj = build_experiment_projection(store, "exp1")
    assert proj is not None
    assert len(proj.chain) == 5
    assert tuple(node["stage"] for node in proj.chain) == CHAIN_ORDER
    assert proj.missing_stages == ()
    # Each chain entry carries a 'stage' key equal to its CHAIN_ORDER value.
    for node, stage in zip(proj.chain, CHAIN_ORDER, strict=True):
        assert node["stage"] == stage
    assert tuple(node["id"] for node in proj.chain) == ("exp1", "s1", "m1", "pr1", "p1")


def test_full_chain_edges_connect_consecutive_ids(store: KuzuGraphStore) -> None:
    proj = build_experiment_projection(store, "exp1")
    assert proj is not None
    assert len(proj.edges) == 4
    ids = [node["id"] for node in proj.chain]
    for i, edge in enumerate(proj.edges):
        assert edge["source"] == ids[i]
        assert edge["target"] == ids[i + 1]
    assert [e["type"] for e in proj.edges] == [
        "HAS_SAMPLE",
        "OF_MATERIAL",
        "PROCESSED_BY",
        "MEASURED_PROPERTY",
    ]


def test_missing_sample_skips_stage_but_edges_still_connect(store: KuzuGraphStore) -> None:
    proj = build_experiment_projection(store, "exp2")
    assert proj is not None
    assert "Sample" in proj.missing_stages
    stages = tuple(node["stage"] for node in proj.chain)
    assert stages == ("Experiment", "Material", "ProcessingRegime", "Property")
    ids = [node["id"] for node in proj.chain]
    assert ids == ["exp2", "m2", "pr2", "p2"]
    # Remaining edges still connect the resolved stages consecutively.
    assert len(proj.edges) == 3
    for i, edge in enumerate(proj.edges):
        assert edge["source"] == ids[i]
        assert edge["target"] == ids[i + 1]


def test_material_only_missing_regime_and_property(store: KuzuGraphStore) -> None:
    proj = build_experiment_projection(store, "exp3")
    assert proj is not None
    assert "ProcessingRegime" in proj.missing_stages
    assert "Property" in proj.missing_stages
    stages = tuple(node["stage"] for node in proj.chain)
    assert stages == ("Experiment", "Sample", "Material")
    assert len(proj.edges) == 2


def test_as_dict_is_camelcase_and_json_serialisable(store: KuzuGraphStore) -> None:
    proj = build_experiment_projection(store, "exp1")
    assert proj is not None
    d = proj.as_dict()
    assert set(d) == {"experimentId", "chain", "edges", "missingStages"}
    assert d["experimentId"] == "exp1"
    assert isinstance(d["chain"], list)
    assert all(isinstance(node, dict) for node in d["chain"])
    # Round-trips through JSON unchanged.
    assert json.loads(json.dumps(d)) == d


def test_frozen_dataclass_is_immutable(store: KuzuGraphStore) -> None:
    proj = build_experiment_projection(store, "exp1")
    assert isinstance(proj, ExperimentProjection)
    with pytest.raises(AttributeError):
        proj.experiment_id = "other"  # type: ignore[misc]
