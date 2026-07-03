"""Provenance-chain builder for a single fact / Measurement (§25.15).

Builds a tiny hand-checkable graph of the provenance path

    Measurement -SUPPORTED_BY-> Evidence -FROM_CHUNK-> Chunk

with the two join-key props set (Evidence ``doc_id`` and Measurement
``extractor_run_id``):

    m1 (run A) -> e1 (docA) -> c1
               -> e2 (docB) -> c2
    m2 (run A) -> e3 (docA) -> c1          # shares chunk c1 with m1/e1
    m3 (run B)                             # run stamp but no evidence at all
    m4 (no run) -> e4 (no doc, no chunk)   # partially missing links

Hand-checked expectations:
- m1 chains fact→source: measurement{m1}, evidence{e1,e2}, chunk{c1,c2}, doc{docA,docB};
- m2 chains measurement{m2}, evidence{e3}, chunk{c1}, doc{docA};
- m3 truncates to the measurement level only (no evidence);
- m4 truncates to measurement+evidence (evidence e4 has no chunk/doc);
- an unknown id yields empty lists, a None run and an empty chain.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.provenance_graph import ProvenanceChain, provenance_chain

RUN_A = "run:2026-07-01"
RUN_B = "run:2026-07-02"
DOC_A = "doc:alpha"
DOC_B = "doc:beta"

M1 = make_id("Measurement", "prov m one")
M2 = make_id("Measurement", "prov m two")
M3 = make_id("Measurement", "prov m three")
M4 = make_id("Measurement", "prov m four")
E1 = make_id("Evidence", "prov e one")
E2 = make_id("Evidence", "prov e two")
E3 = make_id("Evidence", "prov e three")
E4 = make_id("Evidence", "prov e four")
C1 = make_id("Chunk", "prov c one")
C2 = make_id("Chunk", "prov c two")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build_corpus(s)
    yield s
    s.close()


def _build_corpus(s: KuzuGraphStore) -> None:
    """Measurements → Evidence → Chunk with run/doc join keys stamped."""
    s.upsert_node(M1, "Measurement", property_name="recovery", extractor_run_id=RUN_A)
    s.upsert_node(M2, "Measurement", property_name="grade", extractor_run_id=RUN_A)
    s.upsert_node(M3, "Measurement", property_name="yield", extractor_run_id=RUN_B)
    s.upsert_node(M4, "Measurement", property_name="purity")  # no extractor_run_id

    s.upsert_node(E1, "Evidence", text="recovery 92%", doc_id=DOC_A, page=1)
    s.upsert_node(E2, "Evidence", text="recovery 90%", doc_id=DOC_B, page=7)
    s.upsert_node(E3, "Evidence", text="grade 3.1%", doc_id=DOC_A, page=2)
    s.upsert_node(E4, "Evidence", text="purity high")  # no doc_id

    s.upsert_node(C1, "Chunk", text="chunk one")
    s.upsert_node(C2, "Chunk", text="chunk two")

    s.upsert_edge(M1, E1, "SUPPORTED_BY", confidence=1.0)
    s.upsert_edge(M1, E2, "SUPPORTED_BY", confidence=0.9)
    s.upsert_edge(M2, E3, "SUPPORTED_BY", confidence=1.0)
    s.upsert_edge(M4, E4, "SUPPORTED_BY", confidence=0.5)
    s.upsert_edge(E1, C1, "FROM_CHUNK")
    s.upsert_edge(E2, C2, "FROM_CHUNK")
    s.upsert_edge(E3, C1, "FROM_CHUNK")  # e3 also comes from chunk c1
    # e4 has no FROM_CHUNK edge → chunk link is genuinely missing.


# -- full chain measurement -> evidence -> chunk -> doc ---------------------
def test_full_chain_measurement_evidence_chunk_doc(store: KuzuGraphStore) -> None:
    pc = provenance_chain(store, M1)
    assert isinstance(pc, ProvenanceChain)
    assert pc.measurement_id == M1
    assert pc.evidence == sorted([E1, E2])
    assert pc.chunks == sorted([C1, C2])
    assert pc.docs == sorted([DOC_A, DOC_B])
    # The chain carries all four levels, each with its ids.
    kinds = [step["kind"] for step in pc.chain]
    assert kinds == ["measurement", "evidence", "chunk", "doc"]
    by_kind = {step["kind"]: step["ids"] for step in pc.chain}
    assert by_kind["measurement"] == [M1]
    assert by_kind["evidence"] == sorted([E1, E2])
    assert by_kind["chunk"] == sorted([C1, C2])
    assert by_kind["doc"] == sorted([DOC_A, DOC_B])


def test_second_measurement_shared_chunk(store: KuzuGraphStore) -> None:
    pc = provenance_chain(store, M2)
    assert pc.evidence == [E3]
    assert pc.chunks == [C1]  # c1 is shared with m1/e1 but dedup keeps one
    assert pc.docs == [DOC_A]
    assert [step["kind"] for step in pc.chain] == ["measurement", "evidence", "chunk", "doc"]


# -- extractor_run captured ------------------------------------------------
def test_extractor_run_captured(store: KuzuGraphStore) -> None:
    assert provenance_chain(store, M1).extractor_run == RUN_A
    assert provenance_chain(store, M2).extractor_run == RUN_A
    assert provenance_chain(store, M3).extractor_run == RUN_B
    # m4 carries no run stamp → None, read from the prop via get_node.
    assert provenance_chain(store, M4).extractor_run is None


# -- graceful missing links ------------------------------------------------
def test_missing_links_graceful(store: KuzuGraphStore) -> None:
    # m3: has a run stamp but no SUPPORTED_BY evidence → chain stops at measurement.
    pc3 = provenance_chain(store, M3)
    assert pc3.extractor_run == RUN_B
    assert pc3.evidence == []
    assert pc3.chunks == []
    assert pc3.docs == []
    assert [step["kind"] for step in pc3.chain] == ["measurement"]
    assert pc3.chain[0]["ids"] == [M3]

    # m4: evidence e4 exists but has no doc_id and no FROM_CHUNK → truncates there.
    pc4 = provenance_chain(store, M4)
    assert pc4.extractor_run is None
    assert pc4.evidence == [E4]
    assert pc4.chunks == []  # e4 has no FROM_CHUNK edge
    assert pc4.docs == []  # e4 has no doc_id
    assert [step["kind"] for step in pc4.chain] == ["measurement", "evidence"]


# -- unknown id -> empty ---------------------------------------------------
def test_unknown_measurement_id_empty(store: KuzuGraphStore) -> None:
    pc = provenance_chain(store, "measurement:ghost")
    assert pc.measurement_id == "measurement:ghost"
    assert pc.extractor_run is None
    assert pc.evidence == []
    assert pc.chunks == []
    assert pc.docs == []
    assert pc.chain == []  # no node → nothing to chain


def test_empty_store_unknown_empty() -> None:
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    try:
        pc = provenance_chain(s, M1)
        assert pc.extractor_run is None
        assert pc.evidence == []
        assert pc.chunks == []
        assert pc.docs == []
        assert pc.chain == []
    finally:
        s.close()


# -- chain ordered ---------------------------------------------------------
def test_chain_ordered_fact_to_source(store: KuzuGraphStore) -> None:
    # The chain must always run fact→source: measurement then evidence, chunk, doc,
    # never a deeper level ahead of a shallower one.
    order = {"measurement": 0, "evidence": 1, "chunk": 2, "doc": 3}
    for m in (M1, M2, M3, M4):
        kinds = [step["kind"] for step in provenance_chain(store, m).chain]
        ranks = [order[k] for k in kinds]
        assert ranks == sorted(ranks), f"{m} chain not fact→source: {kinds}"
        assert kinds[0] == "measurement"  # a known fact always heads its own chain


# -- serialisation ---------------------------------------------------------
def test_as_dict_shape_and_copy(store: KuzuGraphStore) -> None:
    pc = provenance_chain(store, M1)
    d = pc.as_dict()
    assert set(d) == {"measurement_id", "evidence", "chunks", "docs", "extractor_run", "chain"}
    assert d["measurement_id"] == M1
    assert d["evidence"] == sorted([E1, E2])
    assert d["chunks"] == sorted([C1, C2])
    assert d["docs"] == sorted([DOC_A, DOC_B])
    assert d["extractor_run"] == RUN_A
    assert [step["kind"] for step in d["chain"]] == ["measurement", "evidence", "chunk", "doc"]

    # as_dict deep-copies the id lists and chain — mutation must not touch the value.
    d["evidence"].append("x")
    d["chain"][1]["ids"].append("y")
    assert pc.evidence == sorted([E1, E2])
    assert pc.chain[1]["ids"] == sorted([E1, E2])
