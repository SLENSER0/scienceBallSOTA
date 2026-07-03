"""Tests for GraphRAG source-coverage aggregation (§11.11)."""

from __future__ import annotations

import json

from kg_retrievers.graphrag_source_coverage import (
    SourceCoverage,
    aggregate_sources,
    top_cited,
)


def _two_reports() -> list[dict]:
    return [{"doc_ids": ["d1", "d2"]}, {"doc_ids": ["d2", "d3"]}]


def test_union_of_doc_ids() -> None:
    cov = aggregate_sources(_two_reports())
    assert cov.doc_ids == ("d1", "d2", "d3")
    assert cov.n_docs == 3


def test_per_doc_report_counts() -> None:
    cov = aggregate_sources(_two_reports())
    assert cov.per_doc_reports["d2"] == 2
    assert cov.per_doc_reports["d1"] == 1
    assert cov.per_doc_reports["d3"] == 1


def test_n_reports_and_coverage_ratio() -> None:
    cov = aggregate_sources(_two_reports())
    assert cov.n_reports == 2
    assert cov.coverage_ratio == 1.5


def test_empty_reports() -> None:
    cov = aggregate_sources([])
    assert cov.n_docs == 0
    assert cov.n_reports == 0
    assert cov.doc_ids == ()
    assert cov.coverage_ratio == 0.0


def test_report_with_empty_doc_ids_contributes_nothing() -> None:
    cov = aggregate_sources([{"doc_ids": []}, {"doc_ids": ["d1"]}])
    assert cov.doc_ids == ("d1",)
    assert cov.n_docs == 1
    assert cov.n_reports == 2
    assert cov.per_doc_reports == {"d1": 1}
    assert cov.coverage_ratio == 0.5


def test_top_cited_returns_most_cited() -> None:
    cov = aggregate_sources(_two_reports())
    assert top_cited(cov, 1) == [("d2", 2)]


def test_doc_ids_sorted_and_as_dict_json_serializable() -> None:
    cov = aggregate_sources([{"doc_ids": ["z9", "a1", "m5"]}])
    assert list(cov.doc_ids) == sorted(cov.doc_ids)
    assert cov.doc_ids == ("a1", "m5", "z9")
    payload = cov.as_dict()
    dumped = json.dumps(payload)
    assert json.loads(dumped) == payload
    assert isinstance(cov, SourceCoverage)


def test_custom_doc_key() -> None:
    cov = aggregate_sources([{"sources": ["d1"]}, {"sources": ["d1", "d2"]}], doc_key="sources")
    assert cov.doc_ids == ("d1", "d2")
    assert cov.per_doc_reports["d1"] == 2
    assert cov.coverage_ratio == 1.0


def test_within_report_duplicates_collapse() -> None:
    cov = aggregate_sources([{"doc_ids": ["d1", "d1", "d1"]}])
    assert cov.per_doc_reports["d1"] == 1
    assert cov.n_docs == 1


def test_top_cited_nonpositive_k_empty() -> None:
    cov = aggregate_sources(_two_reports())
    assert top_cited(cov, 0) == []
    assert top_cited(cov, -1) == []
