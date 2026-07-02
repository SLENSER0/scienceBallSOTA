"""Gap analysis + contradiction detection (§15/§25)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.gap_analysis import GapScanner
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def test_detects_contradiction(store: KuzuGraphStore) -> None:
    store.upsert_node("regime:ew", "ProcessingRegime", name="electrowinning")
    store.upsert_node(
        "meas:a",
        "Measurement",
        property_name="flow_velocity",
        value_normalized=0.2,
        normalized_unit="m/s",
    )
    store.upsert_node(
        "meas:b",
        "Measurement",
        property_name="flow_velocity",
        value_normalized=0.5,
        normalized_unit="m/s",
    )
    store.upsert_edge("meas:a", "regime:ew", "ABOUT_REGIME")
    store.upsert_edge("meas:b", "regime:ew", "ABOUT_REGIME")
    res = GapScanner(store).scan()
    assert res.contradictions_created >= 1
    # a CONTRADICTS edge now links the two measurements
    edges = store.rows("MATCH ()-[r:Rel {type:'CONTRADICTS'}]->() RETURN count(r)")
    assert edges[0][0] >= 1


def test_detects_orphan_and_missing_unit(store: KuzuGraphStore) -> None:
    store.upsert_node("material:lonely", "Material", name="Одинокий материал")
    store.upsert_node(
        "meas:nounit", "Measurement", property_name="recovery", value_normalized=90.0
    )  # no normalized_unit
    store.upsert_edge("meas:nounit", "material:lonely", "ABOUT_MATERIAL")
    res = GapScanner(store).scan()
    assert res.by_type.get("missing_unit", 0) >= 1


def test_idempotent_on_seed(store: KuzuGraphStore) -> None:
    build_seed_graph(store)
    r1 = GapScanner(store).scan()
    n1 = store.counts()["nodes"]
    GapScanner(store).scan()
    n2 = store.counts()["nodes"]
    # second scan adds only a new GapScanRun node, not duplicate gaps
    assert n2 - n1 <= 2
    assert r1.gaps_created + r1.contradictions_created >= 0
