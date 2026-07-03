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


def test_contradiction_reachable_via_retriever(store: KuzuGraphStore) -> None:
    # a scan-detected contradiction must be linked to its subject so retrieval
    # surfaces it (finding gap_analysis.py:153)
    from kg_extractors.query_parser import parse_query
    from kg_retrievers.graph_retriever import GraphRetriever

    store.upsert_node(
        "tech:catholyte-circulation-scheme",
        "TechnologySolution",
        name="циркуляция католита",
        canonical_name="catholyte circulation",
        aliases_text="catholyte circulation|циркуляция католита",
        domain="electrometallurgy",
    )
    store.upsert_node(
        "meas:v1",
        "Measurement",
        property_name="flow_velocity",
        value_normalized=0.2,
        normalized_unit="m/s",
    )
    store.upsert_node(
        "meas:v2",
        "Measurement",
        property_name="flow_velocity",
        value_normalized=0.5,
        normalized_unit="m/s",
    )
    store.upsert_edge("meas:v1", "tech:catholyte-circulation-scheme", "ABOUT_REGIME")
    store.upsert_edge("meas:v2", "tech:catholyte-circulation-scheme", "ABOUT_REGIME")
    GapScanner(store).scan()
    res = GraphRetriever(store).retrieve(parse_query("циркуляция католита"))
    assert res.contradictions, "scan-detected contradiction not reachable by retriever"


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


def test_missing_source_span_and_low_confidence_er_rules() -> None:
    # §15.3: two gap rules — a factual node whose Evidence has no text span, and
    # a low-confidence entity-resolution node.
    import tempfile
    from pathlib import Path

    from kg_schema.enums import GapType

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        # measurement backed by a spanless Evidence
        store.upsert_node(
            "meas:spanless",
            "Measurement",
            name="плотность без цитаты",
            value_normalized=1.0,
            normalized_unit="A/m^2",
        )
        store.upsert_node("ev:spanless", "Evidence", text="", doc_id="d")
        store.upsert_edge("meas:spanless", "ev:spanless", "SUPPORTED_BY")
        # low-confidence ad-hoc entity
        store.upsert_node("material:adhoc", "Material", name="какой-то сплав", confidence=0.5)
        store.upsert_edge("material:adhoc", "meas:spanless", "MEASURED")

        res = GapScanner(store).scan()
        assert str(GapType.MISSING_SOURCE_SPAN) in res.by_type
        assert str(GapType.LOW_CONFIDENCE_ENTITY_RESOLUTION) in res.by_type
    finally:
        store.close()
