"""Graph retriever over the seed for the acceptance queries (§24.9)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_extractors.query_parser import parse_query
from kg_retrievers.graph_retriever import GraphRetriever
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def retriever():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    yield GraphRetriever(store)
    store.close()


def test_water_desalination(retriever: GraphRetriever) -> None:
    q = parse_query(
        "Какие методы обессоливания воды подходят, если сульфаты, хлориды, Ca, Mg, Na "
        "по 200–300 мг/л, а сухой остаток ≤1000 мг/дм³?"
    )
    res = retriever.retrieve(q)
    names = " ".join(s.get("name", "") for s in res.solutions).lower()
    assert "осмос" in names or "ионный обмен" in names  # RO / ion exchange found
    assert res.graph is not None and len(res.graph.nodes) > 0


def test_nickel_catholyte(retriever: GraphRetriever) -> None:
    q = parse_query(
        "Какие решения циркуляции католита при электроэкстракции никеля, какая "
        "скорость потока оптимальна?"
    )
    res = retriever.retrieve(q)
    # flow-velocity measurement should surface as a fact
    props = " ".join(f.node.get("property_name", "") for f in res.facts)
    assert "flow_velocity" in props
    # and there should be a contradiction (0.2 vs 0.5 m/s)
    assert res.contradictions


def test_pgm_partition(retriever: GraphRetriever) -> None:
    q = parse_query("распределение Au, Ag и МПГ между штейном и шлаком за последние 5 лет")
    res = retriever.retrieve(q)
    props = " ".join(f.node.get("property_name", "") for f in res.facts)
    assert "distribution_coefficient" in props


def test_gap_query(retriever: GraphRetriever) -> None:
    q = parse_query("нет экспериментов для холодный климат + кучное выщелачивание + никель")
    res = retriever.retrieve(q)
    assert res.gaps  # cold-climate heap-leaching gap present


def test_evidence_present(retriever: GraphRetriever) -> None:
    q = parse_query("обессоливание воды обратный осмос")
    res = retriever.retrieve(q)
    assert res.evidence  # every answer must be evidence-backed
