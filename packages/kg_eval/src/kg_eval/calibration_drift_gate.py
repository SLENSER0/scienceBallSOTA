"""Calibration drift regression gate (§23.25).

Compare two calibration runs — a frozen ``baseline`` and a new ``candidate`` — and
decide whether the candidate has *regressed* on calibration quality. Each run is a
sequence of ``(predicted_confidence, actual_label)`` pairs, scored with the existing
:mod:`kg_eval.calibration_ece` primitives (ECE + Brier).

Sign convention (§23.25: положительная дельта == хуже): every delta is
``candidate − baseline``, so a *positive* delta means the candidate got *worse* (ECE
and Brier are both error metrics where lower is better). A run regresses when either
delta strictly exceeds the tolerance ``tol`` — a delta of exactly ``tol`` passes
(strict ``>``), which keeps the gate stable under floating-point noise at the
threshold.

Регрессионный шлюз детерминирован и не тянет внешних зависимостей: он лишь
переиспользует ``expected_calibration_error`` и ``brier_score``. Пустой кандидат —
ошибка вызова и поднимает ``ValueError`` вместо молчаливого пропуска гейта.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from kg_eval.calibration_ece import brier_score, expected_calibration_error


@dataclass(frozen=True)
class DriftReport:
    """Verdict of a baseline-vs-candidate calibration comparison (§23.25).

    ``ece_baseline``/``ece_candidate`` are the two ECE values; ``ece_delta`` and
    ``brier_delta`` are ``candidate − baseline`` (positive == worse). ``regressed`` is
    ``True`` when either delta strictly exceeds the tolerance, and ``reasons`` names the
    offending metrics (``"ece"`` and/or ``"brier"``) in a stable order.
    """

    ece_baseline: float
    ece_candidate: float
    ece_delta: float
    brier_delta: float
    regressed: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ece_baseline": round(self.ece_baseline, 4),
            "ece_candidate": round(self.ece_candidate, 4),
            "ece_delta": round(self.ece_delta, 4),
            "brier_delta": round(self.brier_delta, 4),
            "regressed": bool(self.regressed),
            "reasons": list(self.reasons),
        }


def check_drift(
    baseline: Sequence[tuple[float, bool]],
    candidate: Sequence[tuple[float, bool]],
    *,
    n_bins: int = 10,
    tol: float = 0.02,
) -> DriftReport:
    """Gate ``candidate`` against ``baseline`` on ECE + Brier drift (§23.25).

    Computes ``ece_delta`` and ``brier_delta`` as ``candidate − baseline`` and flags a
    regression when either strictly exceeds ``tol``. Raises ``ValueError`` if either run
    is empty (a caller bug), delegating the check to the underlying scorers.
    """
    if not baseline:
        raise ValueError("check_drift requires a non-empty baseline run")
    if not candidate:
        raise ValueError("check_drift requires a non-empty candidate run")

    ece_baseline = expected_calibration_error(baseline, n_bins)
    ece_candidate = expected_calibration_error(candidate, n_bins)
    ece_delta = ece_candidate - ece_baseline
    brier_delta = brier_score(candidate) - brier_score(baseline)

    reasons: list[str] = []
    if ece_delta > tol:
        reasons.append("ece")
    if brier_delta > tol:
        reasons.append("brier")

    return DriftReport(
        ece_baseline=ece_baseline,
        ece_candidate=ece_candidate,
        ece_delta=ece_delta,
        brier_delta=brier_delta,
        regressed=bool(reasons),
        reasons=tuple(reasons),
    )
