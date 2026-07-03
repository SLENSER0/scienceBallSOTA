"""Edge-provenance reader over a temp KuzuGraphStore (§8.11).

Builds a tiny hand-checkable graph and reads back the provenance of individual
directed edges:

    N1 -IMPROVES->    N2   evidence {EV1, EV2}, run RUN            (flags default off)
    N2 -CONTRADICTS-> N3   contradicted=True, run RUN
    N1 -CORRELATES->  N3   inferred=True, evidence {EV1}
    N3 -RELATED->     N4   bare edge — no provenance props at all

Hand-checked expectations:
- IMPROVES returns both evidence ids in insertion order and the run stamp;
- CORRELATES surfaces the inferred flag, CONTRADICTS the contradicted flag;
- a bare edge yields empty evidence, no run, both flags False;
- a missing edge (unknown node or wrong rel type) yields None;
- as_dict is a JSON-ready copy that does not alias the frozen tuple.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.edge_provenance import EdgeProvenance, edge_provenance
from kg_retrievers.graph_store import KuzuGraphStore

RUN = "run:2026-07-03"
N1 = make_id("Material", "steel")
N2 = make_id("Property", "hardness")
N3 = make_id("Method", "quench")
N4 = make_id("Paper", "doc alpha")
EV1 = make_id("Evidence", "e one")
EV2 = make_id("Evidence", "e two")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build_corpus(s)
    yield s
    s.close()


def _build_corpus(s: KuzuGraphStore) -> None:
    """Four nodes wired by four edges with distinct provenance stamps."""
    s.upsert_node(N1, "Material", name="Сталь")
    s.upsert_node(N2, "Property", name="Твёрдость")
    s.upsert_node(N3, "Method", name="Закалка")
    s.upsert_node(N4, "Paper", name="Документ")

    # Directly-extracted edge with two evidence ids and a run stamp (flags unset).
    s.upsert_edge(N1, N2, "IMPROVES", evidence_ids=[EV1, EV2], extractor_run_id=RUN)
    # A contradicted edge (red in the UI) carrying the same run stamp.
    s.upsert_edge(N2, N3, "CONTRADICTS", contradicted=True, extractor_run_id=RUN)
    # An inferred edge (dashed in the UI) with a single evidence id, no run stamp.
    s.upsert_edge(N1, N3, "CORRELATES", inferred=True, evidence_ids=[EV1])
    # A bare edge with no provenance props at all.
    s.upsert_edge(N3, N4, "RELATED")


# -- evidence --------------------------------------------------------------
def test_edge_with_evidence_ids_returns_them(store: KuzuGraphStore) -> None:
    prov = edge_provenance(store, N1, N2, "IMPROVES")
    assert isinstance(prov, EdgeProvenance)
    assert prov.src == N1
    assert prov.dst == N2
    assert prov.rel_type == "IMPROVES"
    assert prov.evidence_ids == (EV1, EV2)  # order preserved from insertion
    assert prov.inferred is False  # unset flag defaults to False
    assert prov.contradicted is False


# -- inferred flag ---------------------------------------------------------
def test_inferred_flag(store: KuzuGraphStore) -> None:
    prov = edge_provenance(store, N1, N3, "CORRELATES")
    assert prov is not None
    assert prov.inferred is True  # dashed edge (§5.2.3)
    assert prov.contradicted is False
    assert prov.evidence_ids == (EV1,)
    assert prov.extractor_run_id is None  # this edge carries no run stamp


# -- contradicted flag -----------------------------------------------------
def test_contradicted_flag(store: KuzuGraphStore) -> None:
    prov = edge_provenance(store, N2, N3, "CONTRADICTS")
    assert prov is not None
    assert prov.contradicted is True  # red edge (§5.2.3)
    assert prov.inferred is False
    assert prov.evidence_ids == ()  # no evidence ids on this edge


# -- extractor run capture -------------------------------------------------
def test_extractor_run_captured(store: KuzuGraphStore) -> None:
    assert edge_provenance(store, N1, N2, "IMPROVES").extractor_run_id == RUN
    assert edge_provenance(store, N2, N3, "CONTRADICTS").extractor_run_id == RUN


# -- bare edge defaults ----------------------------------------------------
def test_bare_edge_defaults(store: KuzuGraphStore) -> None:
    prov = edge_provenance(store, N3, N4, "RELATED")
    assert prov is not None
    assert prov.evidence_ids == ()
    assert prov.extractor_run_id is None
    assert prov.inferred is False
    assert prov.contradicted is False


# -- missing edge → None ---------------------------------------------------
def test_missing_edge_returns_none(store: KuzuGraphStore) -> None:
    assert edge_provenance(store, N1, N4, "IMPROVES") is None  # no such edge
    assert edge_provenance(store, "ghost", N2, "IMPROVES") is None  # unknown src
    assert edge_provenance(store, N1, N2, "NOPE") is None  # wrong rel type
    assert edge_provenance(store, N2, N1, "IMPROVES") is None  # wrong direction


# -- serialisation ---------------------------------------------------------
def test_as_dict(store: KuzuGraphStore) -> None:
    prov = edge_provenance(store, N1, N2, "IMPROVES")
    d = prov.as_dict()
    assert set(d) == {
        "src",
        "dst",
        "rel_type",
        "evidence_ids",
        "extractor_run_id",
        "inferred",
        "contradicted",
    }
    assert d["src"] == N1
    assert d["dst"] == N2
    assert d["rel_type"] == "IMPROVES"
    assert d["evidence_ids"] == [EV1, EV2]  # JSON-ready list copy
    assert d["extractor_run_id"] == RUN
    assert d["inferred"] is False
    assert d["contradicted"] is False
    # the dict list is a copy — mutating it must not touch the frozen tuple.
    d["evidence_ids"].append("x")
    assert prov.evidence_ids == (EV1, EV2)


# -- empty store -----------------------------------------------------------
def test_empty_store() -> None:
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    try:
        assert edge_provenance(s, N1, N2, "IMPROVES") is None
    finally:
        s.close()
