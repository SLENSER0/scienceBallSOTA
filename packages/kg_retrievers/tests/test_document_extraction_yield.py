"""Tests for per-document extraction yield (§25.7)."""

from __future__ import annotations

from kg_retrievers.document_extraction_yield import (
    DocYield,
    YieldSummary,
    document_extraction_yield,
)


def _rec(doc_id: str, entity_id: str, prop: str, observed: bool) -> dict:
    return {
        "doc_id": doc_id,
        "entity_id": entity_id,
        "property_name": prop,
        "has_observation": observed,
    }


def test_half_observed_doc_yield_ratio() -> None:
    # Assertion (1): 2 mentioned / 1 observed → yield_ratio == 0.5.
    records = [
        _rec("D1", "E1", "band_gap", True),
        _rec("D1", "E2", "density", False),
    ]
    summary = document_extraction_yield(records)
    d1 = next(d for d in summary.docs if d.doc_id == "D1")
    assert d1.mentioned == 2
    assert d1.observed == 1
    assert d1.yield_ratio == 0.5


def test_missed_contains_unobserved_pair() -> None:
    # Assertion (2): missed lists the un-observed (entity, property) pair.
    records = [
        _rec("D1", "E1", "band_gap", True),
        _rec("D1", "E2", "density", False),
    ]
    summary = document_extraction_yield(records)
    d1 = next(d for d in summary.docs if d.doc_id == "D1")
    assert d1.missed == [("E2", "density")]
    assert ("E1", "band_gap") not in d1.missed


def test_fully_observed_doc() -> None:
    # Assertion (3): fully observed doc → yield_ratio == 1.0 and missed == [].
    records = [
        _rec("D2", "E1", "band_gap", True),
        _rec("D2", "E3", "melting_point", True),
    ]
    summary = document_extraction_yield(records)
    d2 = next(d for d in summary.docs if d.doc_id == "D2")
    assert d2.yield_ratio == 1.0
    assert d2.missed == []


def test_overall_yield_is_total_ratio() -> None:
    # Assertion (4): overall_yield == total_observed / total_mentioned.
    records = [
        _rec("D1", "E1", "band_gap", True),
        _rec("D1", "E2", "density", False),
        _rec("D2", "E1", "band_gap", True),
        _rec("D2", "E3", "melting_point", True),
    ]
    summary = document_extraction_yield(records)
    # 3 observed of 4 mentioned.
    assert summary.overall_yield == 3 / 4


def test_worst_docs_sorted_ascending_and_capped() -> None:
    # Assertion (5): worst_docs ascending by yield, length <= worst_n.
    records = [
        # DA: 0/2 → 0.0 (worst)
        _rec("DA", "E1", "p", False),
        _rec("DA", "E2", "p", False),
        # DB: 1/2 → 0.5
        _rec("DB", "E1", "p", True),
        _rec("DB", "E2", "p", False),
        # DC: 2/2 → 1.0
        _rec("DC", "E1", "p", True),
        _rec("DC", "E2", "p", True),
        # DD: 3/4 → 0.75
        _rec("DD", "E1", "p", True),
        _rec("DD", "E2", "p", True),
        _rec("DD", "E3", "p", True),
        _rec("DD", "E4", "p", False),
    ]
    summary = document_extraction_yield(records, worst_n=3)
    assert len(summary.worst_docs) <= 3
    assert summary.worst_docs == ["DA", "DB", "DD"]
    ratios = {d.doc_id: d.yield_ratio for d in summary.docs}
    ordered = [ratios[doc_id] for doc_id in summary.worst_docs]
    assert ordered == sorted(ordered)


def test_empty_records() -> None:
    # Assertion (6): empty records → overall_yield == 0.0 and docs == [].
    summary = document_extraction_yield([])
    assert summary.overall_yield == 0.0
    assert summary.docs == []
    assert summary.worst_docs == []


def test_zero_mention_doc_excluded() -> None:
    # Assertion (7): a zero-mention doc is excluded from docs.
    # A doc only enters the record stream via mentions, so a doc with an empty
    # mention list simply never appears — verify it stays out of the summary.
    records = [_rec("D1", "E1", "band_gap", True)]
    summary = document_extraction_yield(records)
    doc_ids = {d.doc_id for d in summary.docs}
    assert doc_ids == {"D1"}
    assert "GHOST" not in doc_ids


def test_dataclasses_frozen_and_as_dict() -> None:
    records = [
        _rec("D1", "E1", "band_gap", True),
        _rec("D1", "E2", "density", False),
    ]
    summary = document_extraction_yield(records)
    assert isinstance(summary, YieldSummary)
    assert all(isinstance(d, DocYield) for d in summary.docs)

    d1 = summary.docs[0]
    d1_dict = d1.as_dict()
    assert d1_dict["doc_id"] == "D1"
    assert d1_dict["missed"] == [["E2", "density"]]

    top = summary.as_dict()
    assert top["overall_yield"] == 0.5
    assert top["worst_docs"] == ["D1"]
    assert top["docs"][0]["yield_ratio"] == 0.5
