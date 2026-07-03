"""OCR-need heuristic for scanned-PDF detection (§5.7 OCR branch)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.ocr_decision import (
    REASON_NO_PAGES,
    OcrDecision,
    decide_ocr,
)


def test_all_empty_pages_need_ocr() -> None:
    decision = decide_ocr([0, 0, 0])
    assert decision.needs_ocr is True
    assert decision.empty_page_fraction == 1.0


def test_text_heavy_pages_skip_ocr() -> None:
    decision = decide_ocr([1200, 1500, 900])
    assert decision.needs_ocr is False
    assert decision.empty_page_fraction == 0.0


def test_mean_is_arithmetic_mean() -> None:
    assert decide_ocr([100, 300]).mean_chars_per_page == 200.0


def test_half_empty_at_threshold_triggers_ocr() -> None:
    # [0, 0, 500] with min_chars=100 -> two of three pages empty (2/3 >= 0.5).
    decision = decide_ocr([0, 0, 500], empty_frac_threshold=0.5)
    assert decision.needs_ocr is True


def test_reason_is_non_empty_str() -> None:
    reason = decide_ocr([0, 0, 0]).reason
    assert isinstance(reason, str)
    assert reason


def test_no_pages_never_needs_ocr() -> None:
    decision = decide_ocr([])
    assert decision.needs_ocr is False
    assert decision.reason == REASON_NO_PAGES
    assert decision.mean_chars_per_page == 0.0
    assert decision.empty_page_fraction == 0.0


def test_as_dict_has_all_four_fields() -> None:
    data = decide_ocr([100, 300]).as_dict()
    assert set(data) == {
        "needs_ocr",
        "mean_chars_per_page",
        "empty_page_fraction",
        "reason",
    }


def test_page_just_below_min_chars_counts_empty() -> None:
    # 99 < 100 -> empty; sole page empty -> fraction 1.0 >= 0.5 -> OCR.
    decision = decide_ocr([99])
    assert decision.empty_page_fraction == 1.0
    assert decision.needs_ocr is True


def test_page_at_min_chars_counts_non_empty() -> None:
    # Exactly min_chars is NOT below the threshold -> non-empty page.
    decision = decide_ocr([100])
    assert decision.empty_page_fraction == 0.0
    assert decision.needs_ocr is False


def test_custom_min_chars_reclassifies_pages() -> None:
    # With min_chars=600 both 500-char pages become empty -> OCR.
    assert decide_ocr([500, 500], min_chars=600).needs_ocr is True
    assert decide_ocr([500, 500], min_chars=400).needs_ocr is False


def test_below_threshold_fraction_skips_ocr() -> None:
    # One empty of four -> 0.25 < 0.5 -> no OCR.
    decision = decide_ocr([0, 500, 600, 700])
    assert decision.empty_page_fraction == 0.25
    assert decision.needs_ocr is False


def test_decision_is_frozen() -> None:
    decision = decide_ocr([100, 300])
    with pytest.raises(FrozenInstanceError):
        decision.needs_ocr = True  # type: ignore[misc]


def test_reason_differs_by_verdict() -> None:
    assert "OCR recommended" in decide_ocr([0, 0, 0]).reason
    assert "text layer sufficient" in decide_ocr([1200, 1500]).reason


def test_direct_construction_and_dict_roundtrip() -> None:
    decision = OcrDecision(
        needs_ocr=True,
        mean_chars_per_page=12.5,
        empty_page_fraction=0.75,
        reason="manual",
    )
    assert decision.as_dict() == {
        "needs_ocr": True,
        "mean_chars_per_page": 12.5,
        "empty_page_fraction": 0.75,
        "reason": "manual",
    }
