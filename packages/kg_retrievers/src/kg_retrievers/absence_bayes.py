"""§25.11 — standalone Bayesian absence scorer (P(exists), recall) -> gap verdict.

This module extracts the pure Bayesian math that §25.11's absence layer applies
inline in :mod:`kg_retrievers.absence_signals`, so callers that only need the
probabilities and a verdict — without touching the graph — can reuse it directly.

Given a datum was **not** observed, it is either a настоящий пробел (truly absent)
or an извлечение-miss (it exists but was not extracted). With prior
π = P(exists) and background extraction recall ``r``::

    P(missed | no evidence) = π(1 - r) / (π(1 - r) + (1 - π))
    P(absent | no evidence) = 1 - P(missed | no evidence)

A *high* ``exists_prior`` (we strongly expected the datum) makes an empty cell
read as a miss; a *low* one makes it a genuine gap. Thresholds on P(missed) turn
the posterior into ``possible_miss`` / ``genuine_gap`` / ``abstain``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# -- verdicts --------------------------------------------------------------
POSSIBLE_MISS = "possible_miss"  # extractor probably missed a datum (пропуск)
GENUINE_GAP = "genuine_gap"  # confident real absence (настоящий пробел)
ABSTAIN = "abstain"  # too uncertain to call either way

# -- thresholds on P(extractor missed | no evidence) -----------------------
POSSIBLE_MISS_AT = 0.60  # P(missed) >= this -> possible_miss
GENUINE_GAP_AT = 0.25  # P(missed) <= this -> genuine_gap (otherwise abstain)


def _clamp01(x: float) -> float:
    """Clamp ``x`` into the closed interval ``[0, 1]`` (§25.11 input hygiene)."""
    return max(0.0, min(float(x), 1.0))


@dataclass(frozen=True)
class AbsenceProbabilities:
    """Bayesian absence posteriors plus the thresholded verdict for a datum.

    ``p_truly_absent`` and ``p_extractor_missed`` are the "no evidence" posteriors
    (each in ``[0, 1]``; they sum to 1). ``verdict`` is one of ``possible_miss`` /
    ``genuine_gap`` / ``abstain``.
    """

    p_truly_absent: float
    p_extractor_missed: float
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "p_truly_absent": self.p_truly_absent,
            "p_extractor_missed": self.p_extractor_missed,
            "verdict": self.verdict,
        }


def posterior_absence(exists_prior: float, recall: float) -> tuple[float, float]:
    """One-step Bayesian update on *no evidence* -> ``(p_truly_absent, p_missed)``.

    ``exists_prior`` is π = P(the datum exists); ``recall`` is the background
    extraction recall r. Both are clamped to ``[0, 1]`` first. Returns both
    posteriors, which sum to 1. When the denominator collapses to 0 (π = 1 and
    r = 1: the datum certainly exists and extraction never misses), a no-evidence
    cell cannot be a miss, so ``p_missed = 0``.
    """
    pi = _clamp01(exists_prior)
    r = _clamp01(recall)
    num_missed = pi * (1.0 - r)  # exists yet produced no evidence (a miss)
    num_absent = 1.0 - pi  # truly absent -> no evidence with certainty
    denom = num_missed + num_absent
    if denom <= 0.0:
        return 1.0, 0.0
    p_extractor_missed = num_missed / denom
    p_truly_absent = num_absent / denom
    return p_truly_absent, p_extractor_missed


def verdict_from_probs(
    p_extractor_missed: float,
    *,
    possible_miss_at: float = POSSIBLE_MISS_AT,
    genuine_gap_at: float = GENUINE_GAP_AT,
) -> str:
    """Threshold P(extractor missed) into a verdict (both boundaries inclusive).

    ``>= possible_miss_at`` -> ``possible_miss``; ``<= genuine_gap_at`` ->
    ``genuine_gap``; anything strictly between -> ``abstain``.
    """
    if p_extractor_missed >= possible_miss_at:
        return POSSIBLE_MISS
    if p_extractor_missed <= genuine_gap_at:
        return GENUINE_GAP
    return ABSTAIN


def score_absence(exists_prior: float, recall: float) -> AbsenceProbabilities:
    """Score a no-evidence datum end-to-end -> :class:`AbsenceProbabilities`."""
    p_truly_absent, p_extractor_missed = posterior_absence(exists_prior, recall)
    verdict = verdict_from_probs(p_extractor_missed)
    return AbsenceProbabilities(
        p_truly_absent=p_truly_absent,
        p_extractor_missed=p_extractor_missed,
        verdict=verdict,
    )
