"""GraphRAG citation & evidence traceability over the seed graph (§11.11).

Verifies that community answers stay auditable: SUPPORTED_BY provenance traces to
real Evidence nodes (эвиденс) and their source documents (документы), with dedup.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.community import detect_communities
from kg_retrievers.community_search import global_search
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.graphrag_citations import (
    CommunitySources,
    trace_answer_sources,
    trace_community_hit,
)
from kg_retrievers.seed import build_seed_graph

# Expected provenance of the water-desalination community (seed §24.2 scenario 1).
_WATER_DOC = "desal-review-2022.pdf"
_WATER_EVIDENCE = "ev:desal-review-2022-pdf-ro-removal"


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    detect_communities(s)  # assign community_id + write summaries
    yield s
    s.close()


def _members_of(store: KuzuGraphStore, cid: int) -> list[str]:
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>'Finding' RETURN n.id",
        {"c": cid},
    )
    return [r[0] for r in rows]


def _water_community(store: KuzuGraphStore) -> tuple[int, list[str]]:
    """The community containing reverse osmosis — an evidence-backed cluster."""
    ro = make_id("TechnologySolution", "reverse osmosis desalination")
    node = store.get_node(ro)
    assert node is not None and node.get("community_id") is not None
    cid = int(node["community_id"])
    return cid, _members_of(store, cid)


def test_backed_community_returns_nonempty_doc_ids(store: KuzuGraphStore) -> None:
    cid, members = _water_community(store)
    src = trace_answer_sources(store, members, community_id=cid)
    assert src.doc_ids, "evidence-backed community must yield ≥1 source document"
    assert _WATER_DOC in src.doc_ids
    assert _WATER_EVIDENCE in src.evidence_ids
    assert src.community_id == cid


def test_dedup_across_members(store: KuzuGraphStore) -> None:
    # ro / ie / ed all cite the same single Paper→Evidence→doc, so the aggregate
    # must collapse to exactly one evidence id and one document.
    _, members = _water_community(store)
    src = trace_answer_sources(store, members)
    assert src.evidence_ids == [_WATER_EVIDENCE]
    assert src.doc_ids == [_WATER_DOC]
    # three TechnologySolutions are cited; the Material member carries no provenance.
    assert len(src.cited_entities) == 3
    # no duplicates leaked through anywhere
    assert len(src.evidence_ids) == len(set(src.evidence_ids))
    assert len(src.doc_ids) == len(set(src.doc_ids))
    assert len(src.cited_entities) == len(set(src.cited_entities))


def test_unknown_member_ids_are_graceful(store: KuzuGraphStore) -> None:
    src = trace_answer_sources(store, ["no-such-1", "no-such-2"], community_id=99)
    assert src.doc_ids == []
    assert src.evidence_ids == []
    assert src.cited_entities == []
    assert src.community_id == 99


def test_partial_unknown_still_traces_known(store: KuzuGraphStore) -> None:
    _, members = _water_community(store)
    mixed = ["ghost-a", *members, "ghost-b", members[0]]  # duplicate + unknowns
    src = trace_answer_sources(store, mixed)
    assert _WATER_DOC in src.doc_ids
    assert set(src.cited_entities) <= set(members)


def test_cited_entities_subset_of_members(store: KuzuGraphStore) -> None:
    _, members = _water_community(store)
    src = trace_answer_sources(store, members)
    assert set(src.cited_entities).issubset(set(members))
    assert src.cited_entities, "expected at least one cited entity in a backed community"


def test_as_dict_shape(store: KuzuGraphStore) -> None:
    cid, members = _water_community(store)
    src = trace_answer_sources(store, members, community_id=cid)
    d = src.as_dict()
    assert set(d) == {"community_id", "doc_ids", "evidence_ids", "cited_entities"}
    assert d["community_id"] == cid
    assert isinstance(d["doc_ids"], list)
    assert isinstance(d["evidence_ids"], list)
    assert isinstance(d["cited_entities"], list)
    # returned lists are copies — mutating them must not corrupt the frozen record
    d["doc_ids"].append("tampered")
    assert "tampered" not in src.doc_ids


def test_empty_members_yields_empty_sources(store: KuzuGraphStore) -> None:
    src = trace_answer_sources(store, [])
    assert isinstance(src, CommunitySources)
    assert src.doc_ids == []
    assert src.evidence_ids == []
    assert src.cited_entities == []
    assert src.community_id == -1


def test_trace_community_hit_from_global_search(store: KuzuGraphStore) -> None:
    ans = global_search(store, "осмос ионный обмен вода", limit=3)
    assert ans.communities, "expected a relevant community for the query"
    hit = ans.communities[0]
    src = trace_community_hit(store, hit)
    assert src.community_id == hit.community_id
    assert src.doc_ids, "the top water community must be citation-backed"
    assert set(src.cited_entities).issubset(set(hit.member_ids))
