"""Gap + contradiction detection quality metrics (§15.10 / §18.6).

Set-based precision/recall/F1 for evaluating a gap scan against a golden set of
expected gaps/contradictions. Gaps are keyed by ``(gap_type, subject_id)`` so a
gap of the right type about the right subject counts as a true positive.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


def prf(predicted: Iterable, expected: Iterable) -> PRF:
    """Precision/recall/F1 of two sets of hashable keys."""
    p, e = set(predicted), set(expected)
    tp = len(p & e)
    fp = len(p - e)
    fn = len(e - p)
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if not e else 0.0)
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return PRF(precision, recall, f1, tp, fp, fn)


def _gap_key(g: dict) -> tuple[str, str]:
    """Key a gap by (type, subject id) — resilient to id/field-name variants."""
    gtype = str(g.get("gap_type") or g.get("type") or "")
    subject = str(
        g.get("about") or g.get("subject_id") or g.get("material_id") or g.get("id") or ""
    )
    return (gtype, subject)


def gap_detection_metrics(predicted_gaps: list[dict], expected_gaps: list[dict]) -> dict:
    """PRF over gaps keyed by (gap_type, subject)."""
    return prf(
        (_gap_key(g) for g in predicted_gaps), (_gap_key(g) for g in expected_gaps)
    ).as_dict()


def contradiction_detection_recall(
    predicted_ids: Iterable[str], expected_ids: Iterable[str]
) -> float:
    """Recall of contradiction detection (the costly miss is a false negative)."""
    return prf(predicted_ids, expected_ids).recall
