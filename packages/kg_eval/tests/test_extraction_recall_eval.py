"""Modality-attributed extraction recall against a gold fact set (§25.16)."""

from __future__ import annotations

import pytest

from kg_eval.extraction_recall_eval import (
    ExtractionRecallReport,
    ModalityRecall,
    attribute_modality,
    evaluate_extraction_recall,
)


def _recall_for(report: ExtractionRecallReport, modality: str) -> ModalityRecall:
    (match,) = [m for m in report.by_modality if m.modality == modality]
    return match


def test_table_row_both_extracted_recall_one() -> None:
    # (1) 2 table_row gold, both extracted -> that modality recall == 1.0.
    gold = [
        {"fact_id": "f1", "modality": "table_row"},
        {"fact_id": "f2", "modality": "table_row"},
    ]
    extracted = [{"fact_id": "f1"}, {"fact_id": "f2"}]
    report = evaluate_extraction_recall(gold, extracted)
    tr = _recall_for(report, "table_row")
    assert (tr.n_expected, tr.n_extracted) == (2, 2)
    assert tr.recall == 1.0


def test_chunk_none_extracted_is_blind_spot() -> None:
    # (2) 1 chunk gold, none extracted -> recall == 0.0 and 'chunk' in blind_spots.
    gold = [{"fact_id": "c1", "modality": "chunk"}]
    report = evaluate_extraction_recall(gold, [])
    ch = _recall_for(report, "chunk")
    assert ch.recall == 0.0
    assert "chunk" in report.blind_spots


def test_overall_recall_two_of_three() -> None:
    # (3) 3 gold, 2 matched -> overall_recall == 2/3.
    gold = [
        {"fact_id": "f1", "modality": "table_row"},
        {"fact_id": "f2", "modality": "table_row"},
        {"fact_id": "c1", "modality": "chunk"},
    ]
    extracted = [{"fact_id": "f1"}, {"fact_id": "f2"}]
    report = evaluate_extraction_recall(gold, extracted)
    assert report.overall_recall == pytest.approx(2 / 3)
    assert report.n_expected == 3
    assert report.n_extracted == 2


def test_modality_absent_from_gold_not_in_by_modality() -> None:
    # (4) A modality never present in gold does not appear in by_modality.
    gold = [{"fact_id": "f1", "modality": "table_row"}]
    report = evaluate_extraction_recall(gold, [{"fact_id": "f1"}])
    modalities = {m.modality for m in report.by_modality}
    assert modalities == {"table_row"}
    assert "chunk" not in modalities


def test_attribute_modality_falls_back_to_kind() -> None:
    # (5) attribute_modality({'kind': 'catalog_row'}) == 'catalog_row'.
    assert attribute_modality({"kind": "catalog_row"}) == "catalog_row"
    assert attribute_modality({"modality": "table_row", "kind": "x"}) == "table_row"


def test_attribute_modality_unknown_on_empty() -> None:
    # (6) attribute_modality({}) == 'unknown'.
    assert attribute_modality({}) == "unknown"
    assert attribute_modality({"modality": "", "kind": ""}) == "unknown"


def test_empty_gold_zero_recall_no_blind_spots() -> None:
    # (7) empty gold -> overall_recall == 0.0 and blind_spots == [].
    report = evaluate_extraction_recall([], [{"fact_id": "f1"}])
    assert report.overall_recall == 0.0
    assert report.blind_spots == []
    assert report.by_modality == []
    assert (report.n_expected, report.n_extracted) == (0, 0)


def test_duplicate_extracted_id_not_double_counted() -> None:
    # (8) duplicate extracted fact_id does not double-count matches.
    gold = [
        {"fact_id": "f1", "modality": "table_row"},
        {"fact_id": "f2", "modality": "table_row"},
    ]
    extracted = [{"fact_id": "f1"}, {"fact_id": "f1"}, {"fact_id": "f1"}]
    report = evaluate_extraction_recall(gold, extracted)
    tr = _recall_for(report, "table_row")
    assert tr.n_extracted == 1  # f1 counted once despite 3 dup rows
    assert tr.recall == 0.5
    assert report.overall_recall == 0.5


def test_blind_spot_threshold_is_strict() -> None:
    # recall exactly at threshold is NOT a blind spot (strict <).
    gold = [
        {"fact_id": "a", "modality": "chunk"},
        {"fact_id": "b", "modality": "chunk"},
    ]
    report = evaluate_extraction_recall(gold, [{"fact_id": "a"}], blind_spot_at=0.5)
    assert _recall_for(report, "chunk").recall == 0.5
    assert report.blind_spots == []  # 0.5 is not < 0.5


def test_as_dict_shapes() -> None:
    gold = [
        {"fact_id": "f1", "modality": "table_row"},
        {"fact_id": "c1", "modality": "chunk"},
    ]
    report = evaluate_extraction_recall(gold, [{"fact_id": "f1"}])
    d = report.as_dict()
    assert set(d) == {
        "by_modality",
        "overall_recall",
        "n_expected",
        "n_extracted",
        "blind_spots",
    }
    assert d["overall_recall"] == 0.5
    assert d["blind_spots"] == ["chunk"]
    row = d["by_modality"][0]
    assert set(row) == {"modality", "n_expected", "n_extracted", "recall"}


def test_frozen_dataclasses_immutable() -> None:
    report = evaluate_extraction_recall(
        [{"fact_id": "f1", "modality": "table_row"}], [{"fact_id": "f1"}]
    )
    assert isinstance(report, ExtractionRecallReport)
    assert isinstance(report.by_modality[0], ModalityRecall)
    with pytest.raises(AttributeError):
        report.overall_recall = 0.0  # type: ignore[misc]
    with pytest.raises(AttributeError):
        report.by_modality[0].recall = 1.0  # type: ignore[misc]
