"""Report → text-unit provenance resolver over a hand-built table (§11.11).

A tiny ``text_units`` table with three rows and reports that reference a subset:

    tu-1  doc:alpha  chunk:a1  page 3  span 10..40   (fully populated)
    tu-2  doc:alpha  chunk:a2  page None (no page/span cells)
    tu-3  doc:beta   chunk:b1  page 7  span 0..12

Hand-checked expectations:
- a report referencing {tu-1, tu-3} (2 of 3) yields 2 refs with the right doc/page;
- an unresolved id (tu-99) is silently dropped, no crash;
- evidence_id is deterministic across two calls with the same inputs;
- distinct_doc_ids dedups when two units share doc:alpha;
- page/span round-trip from the source row;
- the default confidence 1.0 propagates to each ref;
- as_dict()['page'] is None when the source row carries no page.
"""

from __future__ import annotations

from kg_retrievers.graphrag_textunit_provenance import (
    EvidenceRef,
    distinct_doc_ids,
    report_to_evidence,
)

TEXT_UNITS = [
    {
        "id": "tu-1",
        "doc_id": "doc:alpha",
        "chunk_id": "chunk:a1",
        "page": 3,
        "span_start": 10,
        "span_end": 40,
    },
    {"id": "tu-2", "doc_id": "doc:alpha", "chunk_id": "chunk:a2"},
    {
        "id": "tu-3",
        "doc_id": "doc:beta",
        "chunk_id": "chunk:b1",
        "page": 7,
        "span_start": 0,
        "span_end": 12,
    },
]


def test_two_of_three_resolved_with_doc_and_page() -> None:
    refs = report_to_evidence("comm:1", ["tu-1", "tu-3"], TEXT_UNITS)
    assert len(refs) == 2
    assert [r.doc_id for r in refs] == ["doc:alpha", "doc:beta"]
    assert refs[0].page == 3
    assert refs[1].page == 7


def test_unresolved_id_silently_dropped() -> None:
    refs = report_to_evidence("comm:1", ["tu-1", "tu-99", "tu-3"], TEXT_UNITS)
    assert len(refs) == 2
    assert [r.chunk_id for r in refs] == ["chunk:a1", "chunk:b1"]


def test_evidence_id_deterministic_across_calls() -> None:
    a = report_to_evidence("comm:1", ["tu-1"], TEXT_UNITS)[0]
    b = report_to_evidence("comm:1", ["tu-1"], TEXT_UNITS)[0]
    assert a.evidence_id == b.evidence_id
    # Different community id changes the derived evidence id.
    c = report_to_evidence("comm:2", ["tu-1"], TEXT_UNITS)[0]
    assert c.evidence_id != a.evidence_id


def test_distinct_doc_ids_dedups_shared_doc() -> None:
    refs = report_to_evidence("comm:1", ["tu-1", "tu-2", "tu-3"], TEXT_UNITS)
    assert len(refs) == 3
    assert distinct_doc_ids(refs) == ["doc:alpha", "doc:beta"]


def test_page_and_span_round_trip() -> None:
    ref = report_to_evidence("comm:1", ["tu-1"], TEXT_UNITS)[0]
    assert ref.page == 3
    assert ref.span_start == 10
    assert ref.span_end == 40
    assert ref.as_dict()["span_start"] == 10
    assert ref.as_dict()["span_end"] == 40


def test_confidence_default_propagates() -> None:
    refs = report_to_evidence("comm:1", ["tu-1", "tu-3"], TEXT_UNITS)
    assert all(r.confidence == 1.0 for r in refs)
    custom = report_to_evidence("comm:1", ["tu-1"], TEXT_UNITS, confidence=0.5)[0]
    assert custom.confidence == 0.5


def test_absent_page_is_none_in_as_dict() -> None:
    ref = report_to_evidence("comm:1", ["tu-2"], TEXT_UNITS)[0]
    assert isinstance(ref, EvidenceRef)
    assert ref.page is None
    assert ref.span_start is None
    d = ref.as_dict()
    assert d["page"] is None
    assert d["doc_id"] == "doc:alpha"
