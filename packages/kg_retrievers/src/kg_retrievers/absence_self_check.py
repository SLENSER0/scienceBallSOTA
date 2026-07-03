"""§25.13 — agent-facing self-check summary over absence-annotated gaps.

Once §25.13 has annotated every suspected пробел with an absence verdict
(:mod:`kg_retrievers.absence_annotate`), an agent that is about to *present*
those gaps — as "unstudied" cells, as hypotheses to chase — needs a compact,
honest read of the batch: how many are настоящие пробелы (genuine gaps) versus
likely пропуски извлечения (extraction misses), how many observations were
retracted, how many the classifier abstained on, and — crucially — whether the
underlying probabilities were *calibrated* at all.

This module rolls a list of annotated-gap dicts into one frozen
:class:`AbsenceSelfCheck`: per-verdict counts, a count of high extractor-miss
risk cells (``p_extractor_missed >= high_miss_at``), a ``calibrated`` flag that
is True only when the batch is non-empty and *every* gap carries calibrated
metadata, and a list of plain RU/EN ``warnings`` the agent should surface
before over-claiming. :func:`should_flag_hypothesis` is the per-gap guard: a
``possible_miss`` or ``abstain`` cell must **not** be presented as unstudied —
it may simply be a datum the extractor dropped — so the agent should hold back.

Read-only. This module touches no graph and adds no queries; it consumes only
the plain dicts produced upstream (the Kuzu note holds transitively — any
custom node props were already read via ``get_node`` upstream, never a RETURN
column).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.absence_signals import (
    ABSTAIN,
    GENUINE_GAP,
    POSSIBLE_MISS,
    RETRACTED,
)

_log = get_logger("absence_self_check")

# Verdicts an agent must NOT present as an unstudied cell: the datum may exist
# but have been missed (possible_miss), or the classifier could not decide
# (abstain). Presenting either as a настоящий пробел would over-claim.
_HOLD_BACK_VERDICTS = frozenset({POSSIBLE_MISS, ABSTAIN})


@dataclass(frozen=True)
class AbsenceSelfCheck:
    """A batch-level honesty summary over §25.13 absence-annotated gaps.

    ``n_gaps`` is the total; ``n_genuine_gap`` / ``n_possible_miss`` /
    ``n_retracted`` / ``n_abstain`` are per-verdict counts; ``n_high_miss_risk``
    counts gaps whose ``p_extractor_missed`` reaches ``high_miss_at``.
    ``calibrated`` is True only for a non-empty batch whose every gap carries
    calibrated metadata. ``warnings`` is a (possibly empty) list of plain RU/EN
    cautions the agent should surface before presenting the gaps.
    """

    n_gaps: int
    n_genuine_gap: int
    n_possible_miss: int
    n_retracted: int
    n_abstain: int
    n_high_miss_risk: int
    calibrated: bool
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_gaps": self.n_gaps,
            "n_genuine_gap": self.n_genuine_gap,
            "n_possible_miss": self.n_possible_miss,
            "n_retracted": self.n_retracted,
            "n_abstain": self.n_abstain,
            "n_high_miss_risk": self.n_high_miss_risk,
            "calibrated": self.calibrated,
            "warnings": list(self.warnings),
        }


def _p_missed(gap: dict) -> float:
    """Read ``p_extractor_missed`` as a float, treating a missing/None value as 0."""
    return float(gap.get("p_extractor_missed") or 0)


def summarize_absence(
    annotated_gaps: list[dict],
    *,
    high_miss_at: float = 0.6,
) -> AbsenceSelfCheck:
    """Roll annotated gaps into an agent-facing §25.13 self-check summary.

    Each gap dict carries an ``absence_verdict`` (the §25.11 vocabulary), an
    optional ``p_extractor_missed`` in ``[0, 1]``, and an optional
    ``absence_meta`` mapping whose ``calibrated`` flag records whether the
    upstream probabilities were calibrated. ``high_miss_at`` is the threshold
    (inclusive) at which a gap counts toward ``n_high_miss_risk``. Read-only.
    """
    counts = Counter(gap.get("absence_verdict") for gap in annotated_gaps)
    n_possible_miss = counts[POSSIBLE_MISS]
    n_high_miss_risk = sum(1 for gap in annotated_gaps if _p_missed(gap) >= high_miss_at)

    calibrated = bool(annotated_gaps) and all(
        gap.get("absence_meta", {}).get("calibrated") for gap in annotated_gaps
    )

    warnings: list[str] = []
    if n_possible_miss > 0:
        warnings.append(
            f"{n_possible_miss} возможных пропуска извлечения — не выдавать как "
            f"пробелы. / {n_possible_miss} possible extraction misses; do not "
            "present as gaps."
        )
    if n_high_miss_risk > 0:
        warnings.append(
            f"{n_high_miss_risk} ячеек с высоким риском пропуска (>= {high_miss_at}). "
            f"/ {n_high_miss_risk} cells at high extractor-miss risk."
        )

    check = AbsenceSelfCheck(
        n_gaps=len(annotated_gaps),
        n_genuine_gap=counts[GENUINE_GAP],
        n_possible_miss=n_possible_miss,
        n_retracted=counts[RETRACTED],
        n_abstain=counts[ABSTAIN],
        n_high_miss_risk=n_high_miss_risk,
        calibrated=calibrated,
        warnings=warnings,
    )
    _log.info(
        "summarize_absence.done",
        n_gaps=check.n_gaps,
        n_high_miss_risk=check.n_high_miss_risk,
        calibrated=check.calibrated,
    )
    return check


def should_flag_hypothesis(gap: dict) -> bool:
    """True when a gap may be presented as unstudied / a hypothesis to chase.

    Returns False for ``possible_miss`` and ``abstain`` verdicts — those may be
    dropped data or undecided cells, so the agent must hold back rather than
    present them as настоящие пробелы. Every other verdict returns True.
    """
    return gap.get("absence_verdict") not in _HOLD_BACK_VERDICTS
