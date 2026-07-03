"""Confidence calibration and uncertainty labelling (§23.25).

Maps a *calibrated* confidence score plus a small set of signal flags to one of
five human-facing labels: ``'high confidence'``, ``'needs review'``,
``'estimated'``, ``'conflicting'`` and ``'unsupported'``. Signal flags take
strict precedence over the raw confidence value so that, e.g., a contradiction
in the evidence is surfaced even when the model reports a high score.

Модель неопределённости (§23.25): флаги сигналов важнее числовой уверенности —
конфликт свидетельств, отсутствие опоры и явная оценка «на глаз» перекрывают
даже высокую калиброванную уверенность, чтобы пользователь видел риск.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

HIGH_CONFIDENCE = "high confidence"
NEEDS_REVIEW = "needs review"
ESTIMATED = "estimated"
CONFLICTING = "conflicting"
UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LabelThresholds:
    """Confidence cut-points for the three numeric bands (§23.25).

    ``high`` — at or above ⇒ ``'high confidence'``; ``review`` — at or above ⇒
    ``'needs review'``; ``low`` — at or above (but below ``review``) still maps
    to ``'needs review'``; below ``low`` ⇒ ``'unsupported'``. Cut-points are
    inclusive lower bounds (``conf >= threshold``).
    """

    high: float = 0.85
    review: float = 0.6
    low: float = 0.3

    def as_dict(self) -> dict[str, float]:
        return {"high": self.high, "review": self.review, "low": self.low}


DEFAULT = LabelThresholds()


def label(
    confidence: float,
    *,
    has_conflict: bool = False,
    has_evidence: bool = True,
    is_estimated: bool = False,
    thresholds: LabelThresholds = DEFAULT,
) -> str:
    """Map a calibrated ``confidence`` and signal flags to one label (§23.25).

    Precedence (first match wins): ``'conflicting'`` if ``has_conflict``; else
    ``'unsupported'`` if not ``has_evidence``; else ``'estimated'`` if
    ``is_estimated``; else the numeric band — ``'high confidence'`` when
    ``confidence >= thresholds.high``, ``'needs review'`` when
    ``confidence >= thresholds.review``, ``'needs review'`` when
    ``confidence >= thresholds.low``, otherwise ``'unsupported'``.
    """
    if has_conflict:
        return CONFLICTING
    if not has_evidence:
        return UNSUPPORTED
    if is_estimated:
        return ESTIMATED
    conf = float(confidence)
    if conf >= thresholds.high:
        return HIGH_CONFIDENCE
    if conf >= thresholds.review:
        return NEEDS_REVIEW
    if conf >= thresholds.low:
        return NEEDS_REVIEW
    return UNSUPPORTED


def label_batch(records: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    """Label a batch of records (§23.25).

    Each record supplies ``'confidence'`` (defaults to ``0.0`` if absent) and,
    optionally, the boolean signal flags ``'has_conflict'``, ``'has_evidence'``
    and ``'is_estimated'`` with the same defaults as :func:`label`.
    """
    out: list[str] = []
    for rec in records:
        out.append(
            label(
                float(rec.get("confidence", 0.0)),  # type: ignore[arg-type]
                has_conflict=bool(rec.get("has_conflict", False)),
                has_evidence=bool(rec.get("has_evidence", True)),
                is_estimated=bool(rec.get("is_estimated", False)),
            )
        )
    return tuple(out)
