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
from agent_service.evidence_assembler import assemble_evidence

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
