"""Observation provenance-lineage over extraction-run join keys (§25.3).

Builds a tiny hand-checkable graph of the provenance path

    Measurement -SUPPORTED_BY-> Evidence -FROM_CHUNK-> Chunk

with the two join-key props set (Evidence ``doc_id`` and Measurement
``extractor_run_id``):

    m1 (run A) -> e1 (docA) -> c1
               -> e2 (docB) -> c2
    m2 (run A) -> e3 (docA) -> c1          # shares chunk c1 with m1/e1
    m3 (run B)                              # no supporting evidence at all
    m4 (no run) -> e4 (no doc, no chunk)    # partially missing links

Hand-checked expectations:
- m1 traces to run A, evidence {e1,e2}, docs {docA,docB}, chunks {c1,c2};
- m2 traces to run A, evidence {e3}, docs {docA}, chunks {c1};
- run A groups {m1,m2}; run B groups {m3};
- m3/m4 exercise graceful missing links; unknown ids stay empty.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.observation_lineage import (
    ObservationLineage,
    observation_lineage,
    observations_by_run,
)

RUN_A = "run:2026-07-01"
RUN_B = "run:2026-07-02"
DOC_A = "doc:alpha"
DOC_B = "doc:beta"

M1 = make_id("Measurement", "m one")
M2 = make_id("Measurement", "m two")
M3 = make_id("Measurement", "m three")
M4 = make_id("Measurement", "m four")
E1 = make_id("Evidence", "e one")
E2 = make_id("Evidence", "e two")
E3 = make_id("Evidence", "e three")
E4 = make_id("Evidence", "e four")
C1 = make_id("Chunk", "c one")
C2 = make_id("Chunk", "c two")


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


# -- full lineage ----------------------------------------------------------
def test_lineage_returns_run_evidence_chunk_doc(store: KuzuGraphStore) -> None:
    lin = observation_lineage(store, M1)
    assert isinstance(lin, ObservationLineage)
    assert lin.measurement_id == M1
    assert lin.extractor_run_id == RUN_A
    assert lin.evidence_ids == sorted([E1, E2])
    assert lin.doc_ids == sorted([DOC_A, DOC_B])
    assert lin.chunk_ids == sorted([C1, C2])


def test_lineage_second_measurement_shared_chunk(store: KuzuGraphStore) -> None:
    lin = observation_lineage(store, M2)
    assert lin.extractor_run_id == RUN_A
    assert lin.evidence_ids == [E3]
    assert lin.doc_ids == [DOC_A]
    assert lin.chunk_ids == [C1]  # c1 is shared with m1 but dedup keeps one


# -- inverse grouping ------------------------------------------------------
def test_observations_by_run_groups(store: KuzuGraphStore) -> None:
    assert observations_by_run(store, RUN_A) == sorted([M1, M2])
    assert observations_by_run(store, RUN_B) == [M3]


def test_observations_by_run_unknown_run_empty(store: KuzuGraphStore) -> None:
    # m4 carries no run stamp, so no run id ever includes it.
    assert observations_by_run(store, "run:does-not-exist") == []


# -- graceful missing links ------------------------------------------------
def test_missing_links_graceful(store: KuzuGraphStore) -> None:
    # m3: has a run stamp but no SUPPORTED_BY evidence at all.
    lin3 = observation_lineage(store, M3)
    assert lin3.extractor_run_id == RUN_B
    assert lin3.evidence_ids == []
    assert lin3.doc_ids == []
    assert lin3.chunk_ids == []

    # m4: evidence e4 exists but has no doc_id and no FROM_CHUNK, run stamp absent.
    lin4 = observation_lineage(store, M4)
    assert lin4.extractor_run_id is None
    assert lin4.evidence_ids == [E4]
    assert lin4.doc_ids == []  # e4 has no doc_id
    assert lin4.chunk_ids == []  # e4 has no FROM_CHUNK edge


# -- unknown id ------------------------------------------------------------
def test_unknown_measurement_id(store: KuzuGraphStore) -> None:
    lin = observation_lineage(store, "measurement:ghost")
    assert lin.measurement_id == "measurement:ghost"
    assert lin.extractor_run_id is None
    assert lin.evidence_ids == []
    assert lin.doc_ids == []
    assert lin.chunk_ids == []


# -- serialisation ---------------------------------------------------------
def test_as_dict_shape_and_copy(store: KuzuGraphStore) -> None:
    lin = observation_lineage(store, M1)
    d = lin.as_dict()
    assert set(d) == {"measurement_id", "extractor_run_id", "evidence_ids", "doc_ids", "chunk_ids"}
    assert d["measurement_id"] == M1
    assert d["extractor_run_id"] == RUN_A
    assert d["evidence_ids"] == sorted([E1, E2])
    assert d["doc_ids"] == sorted([DOC_A, DOC_B])
    assert d["chunk_ids"] == sorted([C1, C2])
    # as_dict copies the lists — mutating the dict must not touch the frozen value.
    d["evidence_ids"].append("x")
    assert lin.evidence_ids == sorted([E1, E2])


# -- empty store -----------------------------------------------------------
def test_empty_store() -> None:
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    try:
        lin = observation_lineage(s, M1)
        assert lin.extractor_run_id is None
        assert lin.evidence_ids == []
        assert lin.doc_ids == []
        assert lin.chunk_ids == []
        assert observations_by_run(s, RUN_A) == []
    finally:
        s.close()
