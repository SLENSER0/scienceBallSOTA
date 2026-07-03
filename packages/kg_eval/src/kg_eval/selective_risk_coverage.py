"""Selective prediction — risk-coverage curve & AURC (§23.25).

A confidence-gated predictor may *abstain* on low-confidence inputs. Ranking
predictions by confidence (descending) and accepting only the top fraction
trades **coverage** (какая доля примеров обслужена) against **selective risk**
(доля ошибок среди принятых). Sweeping the accept-threshold from "accept only
the single most confident" to "accept everything" traces the *risk-coverage
curve*; the area under it (**AURC**) is a single scalar уверенности-качества —
lower is better.

Each record is ``(confidence: float, correct: bool)``: the model's self-reported
confidence and whether that prediction was actually right. This module is
deliberately distinct from its neighbours in §23.25:

* ``calibration_ece.py`` bins confidences and measures |accuracy − confidence|.
* ``abstention_qa_score.py`` scores one *fixed* accept/abstain threshold.
* This module sweeps *every* threshold and integrates the resulting risks.

Curve convention: sort records by confidence descending (stable — ties keep input
order, so the ordering детерминирован). Point ``i`` (0-indexed) accepts the top
``i+1`` records, so ``coverage = (i+1)/n`` and ``risk`` is the fraction incorrect
among those accepted; ``threshold`` is the lowest accepted confidence. There are
exactly ``n`` points with strictly increasing coverage. AURC is the mean of the
pointwise risks. ``risk_at_full_coverage`` is the risk at coverage ``1.0`` — the
overall error rate. Empty input is a caller bug and raises ``ValueError``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CoveragePoint:
    """One point on the risk-coverage curve (§23.25).

    ``coverage`` is the accepted fraction ``(i+1)/n``; ``risk`` the fraction
    incorrect among the accepted top ``i+1`` records; ``threshold`` the lowest
    accepted confidence at this coverage (the accept cut-off).
    """

    coverage: float
    risk: float
    threshold: float

    def as_dict(self) -> dict[str, float]:
        return {
            "coverage": self.coverage,
            "risk": self.risk,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class RiskCoverageReport:
    """Aggregate selective-prediction quality for a set of records (§23.25).

    ``n`` is the number of scored records, ``aurc`` the mean pointwise selective
    risk (area under the risk-coverage curve), ``risk_at_full_coverage`` the
    overall error rate (risk at coverage ``1.0``), and ``points`` the full ordered
    tuple of :class:`CoveragePoint` (length ``n``) for curve rendering.
    """

    n: int
    aurc: float
    risk_at_full_coverage: float
    points: tuple[CoveragePoint, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "aurc": self.aurc,
            "risk_at_full_coverage": self.risk_at_full_coverage,
            "points": [p.as_dict() for p in self.points],
        }


def _sorted_by_confidence(records: Sequence[tuple[float, bool]]) -> list[tuple[float, bool]]:
    """Return ``records`` sorted by confidence descending; stable on ties (§23.25)."""
    if not records:
        raise ValueError("selective_risk_coverage requires at least one record")
    return sorted(records, key=lambda r: r[0], reverse=True)


def risk_at_coverage(records: Sequence[tuple[float, bool]], coverage: float) -> float:
    """Selective risk when accepting the top ``coverage`` fraction (§23.25).

    Records are ranked by confidence descending; the top ``k = ceil(coverage·n)``
    are accepted and the returned risk is the fraction of them that are incorrect.
    ``coverage`` is clamped into ``(0, 1]`` — non-positive values accept a single
    record, values above ``1.0`` accept everything. Raises ``ValueError`` on empty
    input.
    """
    ordered = _sorted_by_confidence(records)
    n = len(ordered)
    c = min(coverage, 1.0)
    k = max(1, min(n, math.ceil(c * n)))
    wrong = sum(1 for _conf, correct in ordered[:k] if not correct)
    return wrong / k


def analyze(records: Sequence[tuple[float, bool]]) -> RiskCoverageReport:
    """Build the full risk-coverage curve, AURC and risk-at-full-coverage (§23.25).

    Sweeps every accept-prefix of the confidence-sorted records, producing exactly
    ``n`` :class:`CoveragePoint` with strictly increasing coverage. Raises
    ``ValueError`` on empty input.
    """
    ordered = _sorted_by_confidence(records)
    n = len(ordered)
    points: list[CoveragePoint] = []
    wrong = 0
    for i, (confidence, correct) in enumerate(ordered):
        if not correct:
            wrong += 1
        k = i + 1
        points.append(CoveragePoint(coverage=k / n, risk=wrong / k, threshold=confidence))
    aurc = sum(p.risk for p in points) / n
    risk_at_full_coverage = points[-1].risk
    return RiskCoverageReport(
        n=n,
        aurc=aurc,
        risk_at_full_coverage=risk_at_full_coverage,
        points=tuple(points),
    )
