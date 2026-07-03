"""Body validation for manual-evidence create — ``POST .../evidence`` (§8.3, §14.8).

Проверяет тело запроса на создание доказательства вручную ещё до записи в
граф: тип источника из фиксированного множества, непустой текст, корректные
смещения символов (``0 <= char_start < char_end``), номер страницы ``>= 1`` и
уверенность в диапазоне ``[0, 1]``. При нарушении поднимается
:class:`EvidenceValidationError`, роутер превращает её в ``422``. Модуль на
чистом stdlib — отдельного места для валидации ручных доказательств не было.

Validates the body of a manual-evidence create request before it is written to
the graph: the source type from a fixed set, non-empty text, well-formed
character offsets (``0 <= char_start < char_end``), a page number ``>= 1`` and a
confidence within ``[0, 1]``. A violation raises
:class:`EvidenceValidationError`, which the router turns into ``422``. Pure
standard library — manual-evidence validation had no home before.

* :data:`VALID_SOURCE_TYPES`      — allowed ``source_type`` values (§8.3).
* :class:`EvidenceValidationError` — raised on any body-validation failure.
* :class:`ValidatedEvidence`      — frozen, validated evidence payload.
* :func:`validate_evidence`       — validate a body → :class:`ValidatedEvidence`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Разрешённые типы источника доказательства / allowed evidence source types (§8.3).
VALID_SOURCE_TYPES: frozenset[str] = frozenset({"text", "table", "manual", "caption", "figure"})


class EvidenceValidationError(ValueError):
    """Некорректное тело создания доказательства / invalid manual-evidence body (§8.3)."""


@dataclass(frozen=True)
class ValidatedEvidence:
    """Неизменяемое проверенное доказательство / frozen validated evidence (§8.3).

    Carries one validated manual-evidence payload: the ``source_type`` (always in
    :data:`VALID_SOURCE_TYPES`), an optional originating ``doc_id``, an optional
    1-based ``page``, an optional character span (``char_start`` / ``char_end``
    with ``0 <= char_start < char_end``), the non-empty ``text`` and an optional
    ``confidence`` within ``[0, 1]``.
    """

    source_type: str
    doc_id: str | None
    page: int | None
    char_start: int | None
    char_end: int | None
    text: str
    confidence: float | None

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for logging and persistence."""
        return {
            "source_type": self.source_type,
            "doc_id": self.doc_id,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "text": self.text,
            "confidence": self.confidence,
        }


def _opt_int(body: Mapping[str, object], key: str) -> int | None:
    """Опциональное целое поле / optional integer field, else ``None`` (§8.3)."""
    if key not in body or body[key] is None:
        return None
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceValidationError(f"{key} must be an integer")
    return value


def validate_evidence(body: Mapping[str, object]) -> ValidatedEvidence:
    """Проверить тело создания доказательства / validate a manual-evidence body (§8.3).

    Enforces, in order: ``source_type`` present and in :data:`VALID_SOURCE_TYPES`,
    a non-empty ``text`` string, a ``page`` (when given) ``>= 1``, character
    offsets that are either both absent or form ``0 <= char_start < char_end``,
    and a ``confidence`` (when given) within ``[0, 1]``. Any breach raises
    :class:`EvidenceValidationError`; on success returns a frozen
    :class:`ValidatedEvidence`.
    """
    source_type = body.get("source_type")
    if not isinstance(source_type, str) or source_type not in VALID_SOURCE_TYPES:
        raise EvidenceValidationError(f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")

    text = body.get("text")
    if not isinstance(text, str) or text == "":
        raise EvidenceValidationError("text must be a non-empty string")

    doc_id_raw = body.get("doc_id")
    if doc_id_raw is not None and not isinstance(doc_id_raw, str):
        raise EvidenceValidationError("doc_id must be a string")
    doc_id: str | None = doc_id_raw

    page = _opt_int(body, "page")
    if page is not None and page < 1:
        raise EvidenceValidationError("page must be >= 1")

    char_start = _opt_int(body, "char_start")
    char_end = _opt_int(body, "char_end")
    if (char_start is None) != (char_end is None):
        raise EvidenceValidationError("char_start and char_end must be given together")
    if char_start is not None and char_end is not None:
        bad_span = char_start < 0 or char_start >= char_end
        if bad_span:
            raise EvidenceValidationError("offsets must satisfy 0 <= char_start < char_end")

    confidence_raw = body.get("confidence")
    confidence: float | None
    if confidence_raw is None:
        confidence = None
    else:
        if isinstance(confidence_raw, bool) or not isinstance(confidence_raw, (int, float)):
            raise EvidenceValidationError("confidence must be a number")
        confidence = float(confidence_raw)
        if confidence < 0.0 or confidence > 1.0:
            raise EvidenceValidationError("confidence must be within [0, 1]")

    return ValidatedEvidence(
        source_type=source_type,
        doc_id=doc_id,
        page=page,
        char_start=char_start,
        char_end=char_end,
        text=text,
        confidence=confidence,
    )
