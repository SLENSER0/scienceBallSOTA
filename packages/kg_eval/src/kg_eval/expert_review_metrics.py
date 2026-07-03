"""Domain-expert validation loop metrics (§23.22 Domain expert validation loop).

Aggregates domain-expert review events into an :class:`ExpertReviewReport`. Each review
carries a ``verdict`` plus the interaction cost of reaching evidence
(``time_to_evidence_s`` and ``clicks_to_verify``). Useful reviews are those the expert
marked ``useful`` or ``trustworthy``; error reviews are those flagged ``wrong_number`` or
``missing_evidence``.

Median convention: the *lower-middle* element of the sorted list — on even counts this is
the element at index ``(n - 1) // 2`` (the lower of the two central values), never their
average. Empty input yields zero rates and zero medians.

Цикл валидации доменным экспертом: доля полезных/доверенных вердиктов, стоимость
проверки (время и клики до свидетельства) и список ошибочных ревью.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Verdicts counted as "useful" (§23.22). ``trustworthy`` is a subset also tracked alone.
USEFUL_VERDICTS: tuple[str, ...] = ("useful", "trustworthy")
TRUST_VERDICT: str = "trustworthy"
# Verdicts flagged as review errors (§23.22).
ERROR_VERDICTS: tuple[str, ...] = ("wrong_number", "missing_evidence")


@dataclass(frozen=True)
class ExpertReviewReport:
    """Aggregated domain-expert review outcome for one validation batch."""

    n_reviews: int
    useful_rate: float
    trust_rate: float
    median_time_to_evidence_s: float
    median_clicks_to_verify: float
    error_review_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialise all six fields; floats rounded to 4 dp, ids as a plain list."""
        return {
            "n_reviews": int(self.n_reviews),
            "useful_rate": round(float(self.useful_rate), 4),
            "trust_rate": round(float(self.trust_rate), 4),
            "median_time_to_evidence_s": round(float(self.median_time_to_evidence_s), 4),
            "median_clicks_to_verify": round(float(self.median_clicks_to_verify), 4),
            "error_review_ids": list(self.error_review_ids),
        }


def _lower_median(values: list[float]) -> float:
    """Lower-middle of ``values``; ``0.0`` when empty.

    Sorts ascending and returns the element at index ``(n - 1) // 2`` — the lower of the
    two central elements on even counts (no averaging).
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[(len(ordered) - 1) // 2])


def aggregate(reviews: Sequence[Mapping[str, object]]) -> ExpertReviewReport:
    """Aggregate expert ``reviews`` into an :class:`ExpertReviewReport`.

    Reads the keys ``id``, ``verdict``, ``time_to_evidence_s`` and ``clicks_to_verify``
    from each review. ``useful_rate`` is the fraction with a verdict in
    :data:`USEFUL_VERDICTS`; ``trust_rate`` is the fraction with verdict ``trustworthy``;
    ``error_review_ids`` is the sorted tuple of ids flagged in :data:`ERROR_VERDICTS`.
    """
    n_reviews = len(reviews)
    if n_reviews == 0:
        return ExpertReviewReport(
            n_reviews=0,
            useful_rate=0.0,
            trust_rate=0.0,
            median_time_to_evidence_s=0.0,
            median_clicks_to_verify=0.0,
            error_review_ids=(),
        )

    useful = 0
    trusted = 0
    times: list[float] = []
    clicks: list[float] = []
    error_ids: list[str] = []
    for review in reviews:
        verdict = review.get("verdict")
        if verdict in USEFUL_VERDICTS:
            useful += 1
        if verdict == TRUST_VERDICT:
            trusted += 1
        if verdict in ERROR_VERDICTS:
            error_ids.append(str(review.get("id")))
        times.append(float(review.get("time_to_evidence_s", 0.0)))
        clicks.append(float(review.get("clicks_to_verify", 0.0)))

    return ExpertReviewReport(
        n_reviews=n_reviews,
        useful_rate=useful / n_reviews,
        trust_rate=trusted / n_reviews,
        median_time_to_evidence_s=_lower_median(times),
        median_clicks_to_verify=_lower_median(clicks),
        error_review_ids=tuple(sorted(error_ids)),
    )
