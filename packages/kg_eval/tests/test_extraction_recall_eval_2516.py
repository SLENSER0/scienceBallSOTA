"""Tests for modality-attributed extraction-recall eval (§25.16)."""

from __future__ import annotations

from kg_eval.extraction_recall_eval_2516 import (
    ExtractionRecallReport,
    ModalityRecall,
    evaluate_extraction_recall,
    fact_key,
)


def _gold() -> list[dict]:
    return [
        {
            "doc_id": "d1",
            "subject": "s1",
            "property_name": "p1",
            "value": "v1",
            "modality": "table_row",
        },
        {
            "doc_id": "d1",
            "subject": "s2",
            "property_name": "p2",
            "value": "v2",
            "modality": "table_row",
        },
        {
            "doc_id": "d1",
            "subject": "s3",
            "property_name": "p3",
            "value": "v3",
            "modality": "chunk",
        },
        {
            "doc_id": "d1",
            "subject": "s4",
            "property_name": "p4",
            "value": "v4",
            "modality": "chunk",
        },
    ]


def test_fact_key_is_the_identity_tuple() -> None:
    fact = {
        "doc_id": "d1",
        "subject": "s1",
        "property_name": "p1",
        "value": "v1",
        "modality": "table_row",
    }
    assert fact_key(fact) == ("d1", "s1", "p1", "v1")


def test_fact_key_missing_keys_read_as_none() -> None:
    assert fact_key({}) == (None, None, None, None)


def test_recall_by_modality_partial_chunk_coverage() -> None:
    gold = _gold()
    # Both table_row facts + 1 of 2 chunk facts extracted.
    extracted = [
        {"doc_id": "d1", "subject": "s1", "property_name": "p1", "value": "v1"},
        {"doc_id": "d1", "subject": "s2", "property_name": "p2", "value": "v2"},
        {"doc_id": "d1", "subject": "s3", "property_name": "p3", "value": "v3"},
    ]
    report = evaluate_extraction_recall(gold, extracted)

    assert isinstance(report, ExtractionRecallReport)
    assert report.by_modality["table_row"].recall == 1.0
    assert report.by_modality["chunk"].recall == 0.5
    assert report.by_modality["table_row"].expected == 2
    assert report.by_modality["table_row"].extracted == 2
    assert report.by_modality["chunk"].expected == 2
    assert report.by_modality["chunk"].extracted == 1
    assert report.overall_recall == 0.75
    assert report.expected_total == 4
    assert report.extracted_total == 3


def test_absent_modality_not_in_by_modality_no_keyerror() -> None:
    report = evaluate_extraction_recall(_gold(), [])
    assert "catalog_row" not in report.by_modality
    # Access must not KeyError-crash the report structure.
    assert set(report.by_modality) == {"table_row", "chunk"}


def test_empty_gold_overall_recall_is_zero() -> None:
    report = evaluate_extraction_recall([], [])
    assert report.overall_recall == 0.0
    assert report.expected_total == 0
    assert report.extracted_total == 0
    assert report.by_modality == {}


def test_duplicate_extracted_facts_do_not_inflate() -> None:
    gold = [
        {
            "doc_id": "d1",
            "subject": "s1",
            "property_name": "p1",
            "value": "v1",
            "modality": "table_row",
        },
    ]
    extracted = [
        {"doc_id": "d1", "subject": "s1", "property_name": "p1", "value": "v1"},
        {"doc_id": "d1", "subject": "s1", "property_name": "p1", "value": "v1"},
    ]
    report = evaluate_extraction_recall(gold, extracted)
    assert report.by_modality["table_row"].extracted == 1
    assert report.by_modality["table_row"].recall == 1.0


def test_modality_recall_as_dict_rounds() -> None:
    mr = ModalityRecall("chunk", 3, 1, 1 / 3)
    assert mr.as_dict() == {
        "modality": "chunk",
        "expected": 3,
        "extracted": 1,
        "recall": 0.3333,
    }


def test_report_as_dict_shape() -> None:
    report = evaluate_extraction_recall(_gold(), [])
    d = report.as_dict()
    assert d["expected_total"] == 4
    assert d["extracted_total"] == 0
    assert d["overall_recall"] == 0.0
    assert d["by_modality"]["chunk"]["expected"] == 2
