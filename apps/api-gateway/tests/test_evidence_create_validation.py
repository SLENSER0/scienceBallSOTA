"""Tests for manual-evidence create body validation (§8.3, §14.8).

Проверяют :func:`validate_evidence`: допустимые типы источника, непустой текст,
корректные смещения символов, номер страницы и уверенность.

Exercise :func:`validate_evidence`: allowed source types, non-empty text,
well-formed offsets, page number and confidence.
"""

from __future__ import annotations

import pytest
from api_gateway.evidence_create_validation import (
    VALID_SOURCE_TYPES,
    EvidenceValidationError,
    ValidatedEvidence,
    validate_evidence,
)


def test_manual_source_type_accepted() -> None:
    """Валидное тело возвращает source_type / valid body keeps source_type."""
    result = validate_evidence({"source_type": "manual", "doc_id": "d", "text": "hi"})
    assert result.source_type == "manual"
    assert result.doc_id == "d"
    assert result.text == "hi"


def test_bogus_source_type_rejected() -> None:
    """Неизвестный тип источника отклоняется / unknown source_type rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "bogus", "text": "x"})


def test_empty_text_rejected() -> None:
    """Пустой текст отклоняется / empty text rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "manual", "text": ""})


def test_inverted_offsets_rejected() -> None:
    """char_start >= char_end отклоняется / inverted offsets rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "manual", "text": "x", "char_start": 5, "char_end": 3})


def test_valid_offsets_kept() -> None:
    """Корректные смещения сохраняются / valid offsets are kept."""
    result = validate_evidence(
        {"source_type": "manual", "text": "x", "char_start": 0, "char_end": 4}
    )
    assert result.char_start == 0
    assert result.char_end == 4


def test_page_zero_rejected() -> None:
    """page < 1 отклоняется / page below 1 rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "manual", "text": "x", "page": 0})


def test_confidence_above_one_rejected() -> None:
    """confidence > 1 отклоняется / confidence above 1 rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "manual", "text": "x", "confidence": 1.2})


def test_as_dict_roundtrip() -> None:
    """as_dict отдаёт source_type / as_dict exposes source_type."""
    result = validate_evidence({"source_type": "manual", "text": "x"})
    assert result.as_dict()["source_type"] == "manual"


def test_all_valid_source_types_accepted() -> None:
    """Каждый тип из множества проходит / every valid source type is accepted."""
    for source_type in VALID_SOURCE_TYPES:
        result = validate_evidence({"source_type": source_type, "text": "t"})
        assert result.source_type == source_type
    assert frozenset({"text", "table", "manual", "caption", "figure"}) == VALID_SOURCE_TYPES


def test_missing_source_type_rejected() -> None:
    """Отсутствие source_type отклоняется / missing source_type rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"text": "x"})


def test_negative_char_start_rejected() -> None:
    """Отрицательный char_start отклоняется / negative char_start rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "text", "text": "x", "char_start": -1, "char_end": 4})


def test_half_offsets_rejected() -> None:
    """Одно смещение без пары отклоняется / lone offset rejected."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "text", "text": "x", "char_start": 0})


def test_confidence_bounds_inclusive() -> None:
    """Границы [0, 1] включительно / confidence bounds 0 and 1 accepted."""
    assert (
        validate_evidence({"source_type": "manual", "text": "x", "confidence": 0.0}).confidence
        == 0.0
    )
    assert (
        validate_evidence({"source_type": "manual", "text": "x", "confidence": 1.0}).confidence
        == 1.0
    )


def test_bool_page_rejected() -> None:
    """bool не считается целым для page / bool is not a valid page int."""
    with pytest.raises(EvidenceValidationError):
        validate_evidence({"source_type": "manual", "text": "x", "page": True})


def test_defaults_are_none() -> None:
    """Опущенные поля равны None / omitted optional fields default to None."""
    result = validate_evidence({"source_type": "figure", "text": "cap"})
    assert isinstance(result, ValidatedEvidence)
    assert result.doc_id is None
    assert result.page is None
    assert result.char_start is None
    assert result.char_end is None
    assert result.confidence is None
