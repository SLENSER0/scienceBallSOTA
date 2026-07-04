"""Evidence-assembler node over a seeded temp store (§13.14).

Deterministic, no LLM: build a temp Kuzu store, seed a fact node plus its
SUPPORTED_BY Evidence spans (mirroring how the graph-store tests seed data), then
assert that :func:`assemble_evidence` deduplicates, orders and numbers the
citations and groups their markers by source document.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_service.evidence_assembler import (
    _order_key,
    _refs_by_node,
    _row_to_ref,
    assemble_evidence,
)

from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _seed_evidence(
    store: KuzuGraphStore,
    ev_id: str,
    *,
    doc_id: str,
    page: int,
    text: str,
    strength: str = "peer_reviewed",
    confidence: float = 0.9,
) -> None:
    """Insert one Evidence node (no edge yet)."""
    store.upsert_node(
        ev_id,
        "Evidence",
        text=text,
        doc_id=doc_id,
        page=page,
        source_type="paragraph",
        evidence_strength=strength,
        confidence=confidence,
    )


def _seed_fact_with_two_evidence(store: KuzuGraphStore) -> str:
    """A Claim fact SUPPORTED_BY two distinct Evidence spans; returns the fact id."""
    fact = "claim:ni-flow"
    store.upsert_node(fact, "Claim", name="оптимальная скорость потока католита")
    _seed_evidence(store, "ev:a", doc_id="doc:paper1", page=3, text="скорость 1.2 см/с")
    _seed_evidence(store, "ev:b", doc_id="doc:paper2", page=7, text="flow velocity 1.1 cm/s")
    store.upsert_edge(fact, "ev:a", "SUPPORTED_BY", confidence=0.9, evidence_ids=["ev:a"])
    store.upsert_edge(fact, "ev:b", "SUPPORTED_BY", confidence=0.8, evidence_ids=["ev:b"])
    return fact


# ---------------------------------------------------------------------------
# Assembly + shape (§13.14)
# ---------------------------------------------------------------------------
def test_assembles_refs_for_node_with_evidence(store: KuzuGraphStore) -> None:
    fact = _seed_fact_with_two_evidence(store)
    result = assemble_evidence(store, [fact])
    assert result.count == 2
    # every citation carries an EvidenceRef with a real span pointer (evidence-first).
    assert all(c.evidence.evidence_id for c in result.citations)
    assert all(c.evidence.source_id == fact for c in result.citations)
    assert {c.evidence.doc_id for c in result.citations} == {"doc:paper1", "doc:paper2"}


def test_as_dict_payload_shape(store: KuzuGraphStore) -> None:
    fact = _seed_fact_with_two_evidence(store)
    payload = assemble_evidence(store, [fact]).as_dict()
    assert set(payload) == {"citations", "by_document", "count"}
    assert payload["count"] == 2
    assert isinstance(payload["citations"], list) and isinstance(payload["by_document"], dict)
    # each serialized citation nests its evidence ref (doc_id/page/text).
    first = payload["citations"][0]
    assert first["marker"] == "[1]"
    assert "evidence" in first and "docId" not in first["evidence"]  # snake dump, not alias


# ---------------------------------------------------------------------------
# Dedup, numbering, grouping
# ---------------------------------------------------------------------------
def test_dedups_identical_evidence(store: KuzuGraphStore) -> None:
    # Two Evidence nodes with different ids but identical doc/page/text are one span.
    fact = "claim:dup"
    store.upsert_node(fact, "Claim", name="дублирующийся довод")
    _seed_evidence(store, "ev:d1", doc_id="doc:same", page=5, text="одинаковый текст")
    _seed_evidence(store, "ev:d2", doc_id="doc:same", page=5, text="одинаковый текст")
    store.upsert_edge(fact, "ev:d1", "SUPPORTED_BY", confidence=0.9)
    store.upsert_edge(fact, "ev:d2", "SUPPORTED_BY", confidence=0.9)
    result = assemble_evidence(store, [fact])
    assert result.count == 1
    assert result.citations[0].marker == "[1]"


def test_numbered_citations_sequential(store: KuzuGraphStore) -> None:
    fact = _seed_fact_with_two_evidence(store)
    result = assemble_evidence(store, [fact])
    markers = sorted(c.marker for c in result.citations)
    assert markers == ["[1]", "[2]"]


def test_groups_by_doc_id(store: KuzuGraphStore) -> None:
    fact = _seed_fact_with_two_evidence(store)
    by_doc = assemble_evidence(store, [fact]).by_document
    assert set(by_doc) == {"doc:paper1", "doc:paper2"}
    # each document contributed exactly one citation marker.
    assert all(len(markers) == 1 for markers in by_doc.values())
    # the union of grouped markers is exactly the numbered citation set.
    all_markers = [m for markers in by_doc.values() for m in markers]
    assert sorted(all_markers) == ["[1]", "[2]"]


# ---------------------------------------------------------------------------
# Ordering (strength, then confidence)
# ---------------------------------------------------------------------------
def test_ordering_by_strength(store: KuzuGraphStore) -> None:
    # A weak-but-confident span must still rank below a strong-but-less-confident one.
    fact = "claim:strength"
    store.upsert_node(fact, "Claim", name="порядок по силе довода")
    _seed_evidence(
        store,
        "ev:weak",
        doc_id="doc:blog",
        page=1,
        text="блог",
        strength="unverified",
        confidence=0.99,
    )
    _seed_evidence(
        store,
        "ev:strong",
        doc_id="doc:journal",
        page=2,
        text="журнал",
        strength="peer_reviewed",
        confidence=0.50,
    )
    store.upsert_edge(fact, "ev:weak", "SUPPORTED_BY")
    store.upsert_edge(fact, "ev:strong", "SUPPORTED_BY")
    citations = assemble_evidence(store, [fact]).citations
    assert citations[0].evidence.evidence_strength == "peer_reviewed"
    assert citations[0].marker == "[1]"
    assert citations[1].evidence.evidence_strength == "unverified"


def test_ordering_confidence_within_strength(store: KuzuGraphStore) -> None:
    # Same strength → the higher-confidence span is numbered first.
    fact = "claim:conf"
    store.upsert_node(fact, "Claim", name="порядок по уверенности")
    _seed_evidence(
        store,
        "ev:lo",
        doc_id="doc:lo",
        page=1,
        text="менее уверенно",
        strength="peer_reviewed",
        confidence=0.60,
    )
    _seed_evidence(
        store,
        "ev:hi",
        doc_id="doc:hi",
        page=1,
        text="более уверенно",
        strength="peer_reviewed",
        confidence=0.95,
    )
    store.upsert_edge(fact, "ev:lo", "SUPPORTED_BY")
    store.upsert_edge(fact, "ev:hi", "SUPPORTED_BY")
    citations = assemble_evidence(store, [fact]).citations
    assert citations[0].evidence.confidence == pytest.approx(0.95)
    assert citations[0].evidence.doc_id == "doc:hi"


# ---------------------------------------------------------------------------
# max_per_claim + empty input
# ---------------------------------------------------------------------------
def test_max_per_claim_caps_evidence(store: KuzuGraphStore) -> None:
    fact = "claim:many"
    store.upsert_node(fact, "Claim", name="много доводов")
    for i in range(4):
        _seed_evidence(
            store,
            f"ev:m{i}",
            doc_id=f"doc:{i}",
            page=i,
            text=f"довод {i}",
            confidence=0.9 - i * 0.1,
        )
        store.upsert_edge(fact, f"ev:m{i}", "SUPPORTED_BY")
    result = assemble_evidence(store, [fact], max_per_claim=2)
    assert result.count == 2
    # the cap keeps the two strongest (highest-confidence) spans, dropping the rest.
    kept = sorted(c.evidence.confidence for c in result.citations)
    assert kept == pytest.approx([0.8, 0.9])


def test_empty_node_ids_returns_empty(store: KuzuGraphStore) -> None:
    result = assemble_evidence(store, [])
    assert result.count == 0
    assert result.citations == ()
    assert result.by_document == {}
    assert result.as_dict() == {"citations": [], "by_document": {}, "count": 0}


# ---------------------------------------------------------------------------
# Batched fetch (N+1 → single query) is behaviour-preserving (§13.14)
# ---------------------------------------------------------------------------
# Reference implementation of the OLD per-node fetch: one query per node id. The
# batched _refs_by_node must reproduce exactly this mapping.
_OLD_SUPPORTED_BY_Q = (
    "MATCH (f:Node {id:$id})-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
    "RETURN e.id, e.doc_id, e.page, e.text, e.evidence_strength, e.confidence"
)


def _old_refs_for_node(store: KuzuGraphStore, node_id: str):  # type: ignore[no-untyped-def]
    """Pre-batch behaviour: a separate SUPPORTED_BY query per fact node (the N+1)."""
    refs = [_row_to_ref(row, node_id) for row in store.rows(_OLD_SUPPORTED_BY_Q, {"id": node_id})]
    refs.sort(key=_order_key)
    return refs


def _ref_tuple(ref):  # type: ignore[no-untyped-def]
    """Value view of an EvidenceRef for order-sensitive equality across the two paths."""
    return (
        ref.evidence_id,
        ref.source_id,
        ref.doc_id,
        ref.page,
        ref.text,
        ref.evidence_strength,
        ref.confidence,
    )


def _seed_second_fact(store: KuzuGraphStore) -> str:
    """A second, independent Claim SUPPORTED_BY its own span; returns the fact id."""
    fact = "claim:ni-temp"
    store.upsert_node(fact, "Claim", name="оптимальная температура")
    _seed_evidence(store, "ev:c", doc_id="doc:paper3", page=4, text="температура 60 C")
    store.upsert_edge(fact, "ev:c", "SUPPORTED_BY", confidence=0.7, evidence_ids=["ev:c"])
    return fact


def test_refs_by_node_matches_per_node_loop(store: KuzuGraphStore) -> None:
    # Batched grouping over the whole set == the old query-per-node mapping, order-exact.
    fact_a = _seed_fact_with_two_evidence(store)
    fact_b = _seed_second_fact(store)
    node_ids = [fact_a, fact_b, "claim:missing"]  # includes a node with no evidence

    batched = _refs_by_node(store, node_ids)
    expected = {nid: _old_refs_for_node(store, nid) for nid in node_ids}

    # A node with no SUPPORTED_BY edges is simply absent from the grouping (old loop
    # returned [] for it; both yield no citations downstream).
    assert set(batched) == {fact_a, fact_b}
    for nid in (fact_a, fact_b):
        assert [_ref_tuple(r) for r in batched[nid]] == [_ref_tuple(r) for r in expected[nid]]


def test_multi_node_grouping_attributes_source_id(store: KuzuGraphStore) -> None:
    # Each fact's spans stay attributed to that fact under the single batched read.
    fact_a = _seed_fact_with_two_evidence(store)
    fact_b = _seed_second_fact(store)
    result = assemble_evidence(store, [fact_a, fact_b])
    assert result.count == 3  # two spans from A + one from B, all distinct docs
    by_source: dict[str, set[str]] = {}
    for c in result.citations:
        by_source.setdefault(c.evidence.source_id, set()).add(c.evidence.doc_id)
    assert by_source == {
        fact_a: {"doc:paper1", "doc:paper2"},
        fact_b: {"doc:paper3"},
    }


def test_multi_node_dedups_span_shared_across_facts(store: KuzuGraphStore) -> None:
    # Same (doc,page,text) span supporting two different facts is one citation, and the
    # first fact in node_ids order wins the citation (dedup order preserved).
    fact_a = "claim:a"
    fact_b = "claim:b"
    store.upsert_node(fact_a, "Claim", name="факт A")
    store.upsert_node(fact_b, "Claim", name="факт B")
    _seed_evidence(store, "ev:sa", doc_id="doc:shared", page=2, text="общий довод")
    _seed_evidence(store, "ev:sb", doc_id="doc:shared", page=2, text="общий довод")
    store.upsert_edge(fact_a, "ev:sa", "SUPPORTED_BY", confidence=0.9)
    store.upsert_edge(fact_b, "ev:sb", "SUPPORTED_BY", confidence=0.9)

    result = assemble_evidence(store, [fact_a, fact_b])
    assert result.count == 1
    assert result.citations[0].evidence.source_id == fact_a  # first claim keeps the span
