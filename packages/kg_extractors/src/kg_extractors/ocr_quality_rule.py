"""Rule ``low_quality_ocr`` — mint review-task drafts from per-evidence OCR score (§16.5).

Distinct from the parse-time ``ocr_decision`` (which chooses whether to accept a
page's OCR at ingest): this rule runs *after* extraction and mints review-task
drafts from the OCR quality attached to each **evidence** span. A low ``ocr_score``
means the underlying glyphs are unreliable, so any claim resting on that evidence
should be routed to a human. Table cells face a stricter bar — a mis-read digit in
a composition or property table silently corrupts numbers — so they trip the rule
at a higher score than free text.

Правило ``low_quality_ocr``: черновики задач ревью по OCR-качеству улик (§16.5).
Для ячеек таблиц порог строже, чем для текста.

Pure python — no dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Default acceptance bars (§16.5). Text below ``min_ocr_score`` is low-quality;
# table cells use the stricter ``table_cell_min`` because a mis-read digit is silent.
DEFAULT_MIN_OCR_SCORE = 0.6
DEFAULT_TABLE_CELL_MIN = 0.75

TASK_TYPE = "low_quality_ocr"


@dataclass(frozen=True)
class OcrReviewFinding:
    """One evidence span whose OCR score is below its acceptance bar (§16.5)."""

    evidence_id: str
    doc_id: str
    page: int
    ocr_score: float
    source_type: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_type": TASK_TYPE,
            "evidence_id": self.evidence_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "ocr_score": self.ocr_score,
            "source_type": self.source_type,
            "reason": self.reason,
        }


def _score_of(evidence: Mapping[str, Any]) -> float:
    """Read ``ocr_score`` defensively, defaulting missing/None to ``0.0`` (§16.5)."""
    raw = evidence.get("ocr_score")
    if raw is None:
        return 0.0
    return float(raw)


def is_low_quality(
    evidence: Mapping[str, Any],
    *,
    min_ocr_score: float = DEFAULT_MIN_OCR_SCORE,
    table_cell_min: float = DEFAULT_TABLE_CELL_MIN,
) -> bool:
    """True iff *evidence* fails its OCR bar (§16.5).

    Fails when ``ocr_score < min_ocr_score``, or when ``source_type == 'table_cell'``
    and ``ocr_score < table_cell_min`` (the stricter table-cell bar). A missing
    ``ocr_score`` key is treated as ``0.0`` and therefore always low-quality.
    """
    score = _score_of(evidence)
    if score < min_ocr_score:
        return True
    source_type = evidence.get("source_type")
    return source_type == "table_cell" and score < table_cell_min


def _reason_for(
    score: float,
    source_type: str,
    *,
    min_ocr_score: float,
    table_cell_min: float,
) -> str:
    """Human-readable reason naming the threshold that was breached (§16.5)."""
    if source_type == "table_cell" and score < table_cell_min and score >= min_ocr_score:
        return (
            f"table_cell ocr_score {score:.3g} below stricter table-cell "
            f"threshold {table_cell_min:.3g}"
        )
    return f"ocr_score {score:.3g} below threshold {min_ocr_score:.3g}"


def detect(
    evidences: Sequence[Mapping[str, Any]],
    *,
    min_ocr_score: float = DEFAULT_MIN_OCR_SCORE,
    table_cell_min: float = DEFAULT_TABLE_CELL_MIN,
) -> list[OcrReviewFinding]:
    """Emit one :class:`OcrReviewFinding` per low-quality evidence in *evidences* (§16.5)."""
    findings: list[OcrReviewFinding] = []
    for evidence in evidences:
        if not is_low_quality(evidence, min_ocr_score=min_ocr_score, table_cell_min=table_cell_min):
            continue
        score = _score_of(evidence)
        source_type = str(evidence.get("source_type", ""))
        reason = _reason_for(
            score,
            source_type,
            min_ocr_score=min_ocr_score,
            table_cell_min=table_cell_min,
        )
        findings.append(
            OcrReviewFinding(
                evidence_id=str(evidence.get("evidence_id", "")),
                doc_id=str(evidence.get("doc_id", "")),
                page=int(evidence.get("page", 0)),
                ocr_score=score,
                source_type=source_type,
                reason=reason,
            )
        )
    return findings
