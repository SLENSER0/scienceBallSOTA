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


# -- n+1 batching optimization: batched neigh/edge == per-candidate loop --------
def _batched_maps(retriever: GraphRetriever, cand_ids: list[str]):  # type: ignore[no-untyped-def]
    """Replicate retrieve()'s two batched queries → (neigh_map, edge_ev_map)."""
    import json as _json

    store = retriever.store
    neigh_map: dict[str, list] = {}
    edge_ev_map: dict[str, set] = {}
    for row in store.rows(
        "MATCH (a:Node)-[e:Rel]-(b:Node) WHERE a.id IN $ids RETURN a.id, b, e.type",
        {"ids": cand_ids},
    ):
        neigh_map.setdefault(row[0], []).append((store._node_dict(row[1]), row[2]))
    for row in store.rows(
        "MATCH (a:Node)-[e:Rel]-(:Node) WHERE a.id IN $ids "
        "AND e.evidence_ids IS NOT NULL RETURN a.id, e.evidence_ids",
        {"ids": cand_ids},
    ):
        try:
            edge_ev_map.setdefault(row[0], set()).update(_json.loads(row[1]))
        except (_json.JSONDecodeError, TypeError):
            continue
    return neigh_map, edge_ev_map


def test_batched_assembly_matches_per_candidate_loop() -> None:
    """The 2 batched WHERE-id-IN queries reconstruct the exact per-candidate results
    the old 2*N _POOL.map(self._neighbors / self._edge_evidence_ids) loop produced."""
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        for nid in ("A", "B", "C", "D"):
            store.upsert_node(nid, "Node", name=nid)
        store.upsert_edge("A", "B", "REL1", evidence_ids=["ev1"])
        store.upsert_edge("A", "C", "REL2")
        store.upsert_edge("C", "D", "REL3", evidence_ids=["ev2", "ev3"])
        retriever = GraphRetriever(store)
        cand_ids = ["A", "C", "Z"]  # Z is absent → must behave like empty result

        # old path: one query per candidate
        old_neigh = {cid: retriever._neighbors(cid) for cid in cand_ids}
        old_edge = {cid: retriever._edge_evidence_ids(cid) for cid in cand_ids}
        # new path: two batched queries, grouped by a.id
        new_neigh, new_edge = _batched_maps(retriever, cand_ids)

        def _key(pairs):  # type: ignore[no-untyped-def]
            return sorted((nd["id"], rt) for nd, rt in pairs)

        for cid in cand_ids:
            # .get default mirrors retrieve()'s neigh_map.get(cid, []) / (cid, set())
            assert _key(new_neigh.get(cid, [])) == _key(old_neigh[cid])
            assert new_edge.get(cid, set()) == old_edge[cid]
        # sanity: the fixture actually exercises neighbours + edge evidence
        assert _key(old_neigh["A"]) == [("B", "REL1"), ("C", "REL2")]
        assert old_edge["A"] == {"ev1"}
        assert old_edge["C"] == {"ev2", "ev3"}
        assert old_neigh["Z"] == [] and old_edge["Z"] == set()
    finally:
        store.close()
