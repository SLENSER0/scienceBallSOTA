"""Community-report confidence propagation (§11.11).

Aggregates per-member evidence *confidence* and *review_status* into a single
report-level verdict so the §11.11 verifier can downgrade unverified community
summaries. ``graphrag_answer_verify`` only checks numeric grounding; there is no
report-confidence aggregator, which this module provides.

Агрегирует уверенность и статус проверки участников сообщества в отчётную
уверенность, чтобы верификатор §11.11 мог понижать непроверенные сводки.

Aggregation rules:
- ``confidence`` — arithmetic mean of ``member_confidences`` (``0.0`` if empty);
- ``n_supported`` — count of confidences ``>= support_threshold``;
- ``review_status`` — ``'rejected'`` if any member is ``'rejected'``; else
  ``'accepted'`` if the list is non-empty and every member is ``'accepted'``;
  otherwise ``'pending'``.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CommunityConfidence:
    """Report-level confidence verdict for one community (§11.11).

    - ``community_id`` — id of the aggregated community;
    - ``confidence`` — mean member confidence in ``[0, 1]`` (``0.0`` if empty);
    - ``review_status`` — ``'rejected'`` / ``'accepted'`` / ``'pending'``;
    - ``n_supported`` — number of members at or above the support threshold;
    - ``n_members`` — number of member confidences aggregated.
    """

    community_id: str
    confidence: float
    review_status: str
    n_supported: int
    n_members: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping of this verdict."""
        return {
            "community_id": self.community_id,
            "confidence": self.confidence,
            "review_status": self.review_status,
            "n_supported": self.n_supported,
            "n_members": self.n_members,
        }


def aggregate_confidence(
    community_id: str,
    member_confidences: Sequence[float],
    review_statuses: Sequence[str],
    support_threshold: float = 0.5,
) -> CommunityConfidence:
    """Aggregate member evidence into a report-level :class:`CommunityConfidence`.

    ``confidence`` is the arithmetic mean of ``member_confidences`` (``0.0`` when
    empty). ``n_supported`` counts confidences ``>= support_threshold``. The
    ``review_status`` is ``'rejected'`` if any status is ``'rejected'``; else
    ``'accepted'`` when the statuses are non-empty and all are ``'accepted'``;
    otherwise ``'pending'``.
    """
    n_members = len(member_confidences)
    confidence = sum(member_confidences) / n_members if n_members else 0.0
    n_supported = sum(1 for c in member_confidences if c >= support_threshold)

    if any(status == "rejected" for status in review_statuses):
        review_status = "rejected"
    elif review_statuses and all(status == "accepted" for status in review_statuses):
        review_status = "accepted"
    else:
        review_status = "pending"

    return CommunityConfidence(
        community_id=community_id,
        confidence=confidence,
        review_status=review_status,
        n_supported=n_supported,
        n_members=n_members,
    )
