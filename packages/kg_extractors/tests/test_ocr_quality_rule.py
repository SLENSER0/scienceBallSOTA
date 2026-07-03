"""Tests for rule ``low_quality_ocr`` (§16.5)."""

from __future__ import annotations

from kg_extractors.ocr_quality_rule import (
    TASK_TYPE,
    OcrReviewFinding,
    detect,
    is_low_quality,
)


def test_high_score_text_not_low() -> None:
    ev = {"evidence_id": "e1", "doc_id": "d1", "page": 1, "ocr_score": 0.9, "source_type": "text"}
    assert is_low_quality(ev) is False


def test_low_score_text_is_low() -> None:
    ev = {"evidence_id": "e2", "doc_id": "d1", "page": 2, "ocr_score": 0.5, "source_type": "text"}
    assert is_low_quality(ev) is True


def test_low_score_text_reason_mentions_threshold() -> None:
    ev = {"evidence_id": "e2", "doc_id": "d1", "page": 2, "ocr_score": 0.5, "source_type": "text"}
    findings = detect([ev])
    assert len(findings) == 1
    assert "threshold" in findings[0].reason
    assert "0.6" in findings[0].reason


def test_table_cell_0_7_is_low_below_stricter_bar() -> None:
    # 0.7 clears the text bar (0.6) but not the stricter table-cell bar (0.75).
    ev = {
        "evidence_id": "c1",
        "doc_id": "d2",
        "page": 3,
        "ocr_score": 0.7,
        "source_type": "table_cell",
    }
    assert is_low_quality(ev) is True


def test_table_cell_0_8_not_low() -> None:
    ev = {
        "evidence_id": "c2",
        "doc_id": "d2",
        "page": 3,
        "ocr_score": 0.8,
        "source_type": "table_cell",
    }
    assert is_low_quality(ev) is False


def test_table_cell_reason_names_stricter_bar() -> None:
    ev = {
        "evidence_id": "c1",
        "doc_id": "d2",
        "page": 3,
        "ocr_score": 0.7,
        "source_type": "table_cell",
    }
    findings = detect([ev])
    assert len(findings) == 1
    assert "table-cell" in findings[0].reason
    assert "0.75" in findings[0].reason


def test_as_dict_task_type_and_provenance() -> None:
    ev = {"evidence_id": "e2", "doc_id": "d9", "page": 7, "ocr_score": 0.4, "source_type": "text"}
    finding = detect([ev])[0]
    d = finding.as_dict()
    assert d["task_type"] == TASK_TYPE == "low_quality_ocr"
    assert d["doc_id"] == "d9"
    assert d["page"] == 7
    assert d["evidence_id"] == "e2"


def test_missing_ocr_score_key_treated_as_low() -> None:
    ev = {"evidence_id": "e3", "doc_id": "d1", "page": 1, "source_type": "text"}
    assert is_low_quality(ev) is True
    finding = detect([ev])[0]
    assert finding.ocr_score == 0.0


def test_none_ocr_score_treated_as_low() -> None:
    ev = {"evidence_id": "e4", "doc_id": "d1", "page": 1, "ocr_score": None, "source_type": "text"}
    assert is_low_quality(ev) is True


def test_detect_mixed_batch_of_three_yields_two() -> None:
    evidences = [
        # bad text (0.5 < 0.6)
        {"evidence_id": "b1", "doc_id": "d1", "page": 1, "ocr_score": 0.5, "source_type": "text"},
        # bad cell (0.7 < 0.75)
        {
            "evidence_id": "b2",
            "doc_id": "d1",
            "page": 2,
            "ocr_score": 0.7,
            "source_type": "table_cell",
        },
        # good text (0.95)
        {"evidence_id": "g1", "doc_id": "d1", "page": 3, "ocr_score": 0.95, "source_type": "text"},
    ]
    findings = detect(evidences)
    assert len(findings) == 2
    assert {f.evidence_id for f in findings} == {"b1", "b2"}


def test_boundary_score_equal_to_bar_not_low() -> None:
    # ocr_score exactly at the threshold is accepted (strict <).
    text = {"evidence_id": "t", "doc_id": "d", "page": 1, "ocr_score": 0.6, "source_type": "text"}
    cell = {
        "evidence_id": "c",
        "doc_id": "d",
        "page": 1,
        "ocr_score": 0.75,
        "source_type": "table_cell",
    }
    assert is_low_quality(text) is False
    assert is_low_quality(cell) is False


def test_table_cell_below_text_bar_uses_text_reason() -> None:
    # 0.5 fails even the text bar, so the reason cites min_ocr_score, not the cell bar.
    ev = {
        "evidence_id": "c3",
        "doc_id": "d",
        "page": 1,
        "ocr_score": 0.5,
        "source_type": "table_cell",
    }
    finding = detect([ev])[0]
    assert "0.6" in finding.reason


def test_custom_thresholds_respected() -> None:
    ev = {"evidence_id": "x", "doc_id": "d", "page": 1, "ocr_score": 0.65, "source_type": "text"}
    assert is_low_quality(ev, min_ocr_score=0.7) is True
    assert is_low_quality(ev, min_ocr_score=0.6) is False


def test_finding_is_frozen() -> None:
    finding = OcrReviewFinding(
        evidence_id="e", doc_id="d", page=1, ocr_score=0.1, source_type="text", reason="r"
    )
    try:
        finding.ocr_score = 0.9  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("OcrReviewFinding must be frozen")
