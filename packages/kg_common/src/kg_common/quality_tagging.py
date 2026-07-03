"""Auto-assign a quality tag from aggregate review evidence (§10.11 качество).

A dataset or document accumulates *evidence* rows, each carrying a curator
``review_status`` (``accepted`` / ``pending`` / ``rejected``). This module rolls
those statuses up into a single :class:`QualityAssessment` and derives a coarse
quality *tag* for the parent asset (тег качества):

    tag == "verified"   iff  total > 0  and  accepted_ratio >= threshold
    tag == "pending"    otherwise (in particular when no evidence exists)

Per §10.11 the tag flips to ``quality:pending`` as soon as the accepted ratio
drops below the acceptance threshold (доля принятых ниже порога -> pending).

Pure and deterministic — no store, no I/O. The status stream is passed in by the
caller so the numbers are fully hand-checkable. Unknown status strings (anything
outside the three known values) are simply ignored and never counted toward the
total (неизвестные статусы игнорируются).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

# -- known evidence review statuses (§10.11 статусы ревью) -----------------
STATUS_ACCEPTED = "accepted"
STATUS_PENDING = "pending"
STATUS_REJECTED = "rejected"
_KNOWN_STATUSES = frozenset({STATUS_ACCEPTED, STATUS_PENDING, STATUS_REJECTED})

# -- derived quality tags (производный тег качества) -----------------------
TAG_VERIFIED = "verified"  # доля принятых достигла порога
TAG_PENDING = "pending"  # порог не достигнут либо нет свидетельств

_RATIO_PRECISION = 6  # округление доли (гасим шум float в отображении)


@dataclass(frozen=True)
class QualityAssessment:
    """Rolled-up quality verdict for one asset — свод качества (§10.11).

    Fields
    ------
    total:
        Count of *known* evidence statuses (без учёта неизвестных).
    accepted / pending / rejected:
        Per-status counts among the known statuses (счётчики по статусу).
    accepted_ratio:
        ``accepted / total`` in ``[0.0, 1.0]``; ``0.0`` when ``total == 0``
        (доля принятых свидетельств).
    tag:
        ``"verified"`` or ``"pending"`` per the module rule (итоговый тег).
    """

    total: int
    accepted: int
    pending: int
    rejected: int
    accepted_ratio: float
    tag: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` of every field, ``tag`` included (сериализация)."""
        return asdict(self)


def assess_quality(
    review_statuses: Iterable[str],
    threshold: float = 0.8,
) -> QualityAssessment:
    """Assess asset quality from a stream of evidence review statuses (§10.11).

    Parameters
    ----------
    review_statuses:
        Iterable of ``review_status`` strings; only ``accepted`` / ``pending`` /
        ``rejected`` are counted, everything else is ignored (игнор неизвестных).
    threshold:
        Minimum accepted ratio for the ``verified`` tag (порог принятия),
        default ``0.8``.

    Returns
    -------
    QualityAssessment
        Counts, the accepted ratio and the derived tag. The tag is ``verified``
        iff ``total > 0`` and ``accepted_ratio >= threshold``, else ``pending``.
    """
    accepted = pending = rejected = 0
    for status in review_statuses:
        if status == STATUS_ACCEPTED:
            accepted += 1
        elif status == STATUS_PENDING:
            pending += 1
        elif status == STATUS_REJECTED:
            rejected += 1
        # unknown statuses are ignored (не входят в total)

    total = accepted + pending + rejected
    accepted_ratio = round(accepted / total, _RATIO_PRECISION) if total else 0.0
    tag = TAG_VERIFIED if total > 0 and accepted_ratio >= threshold else TAG_PENDING

    return QualityAssessment(
        total=total,
        accepted=accepted,
        pending=pending,
        rejected=rejected,
        accepted_ratio=accepted_ratio,
        tag=tag,
    )
