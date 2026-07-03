"""Rule ``ambiguous_er`` — flag entity-resolution decisions needing human review (§16.5).

Splink-style entity resolution emits, per mention cluster, a set of candidate
matches with a ``match_probability`` each (and optionally a ``decision``). A
cluster is *ambiguous* when the ER pipeline itself asks for review
(``decision == 'review_needed'``) or when the top two candidates are too close —
the margin between the best and second-best ``match_probability`` falls below a
threshold. This module turns such clusters into review-task payloads so a human
can pick the canonical entity. A cluster with a clear winner, or with a single
candidate (no runner-up to be confused with), yields no finding.

Правило ``ambiguous_er``: помечает решения ER, требующие ручной проверки (§16.5).

Pure python — no dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AmbiguousErFinding:
    """One entity-resolution cluster whose canonical entity is ambiguous (§16.5)."""

    candidate_id: str
    mentions: tuple[str, ...]
    top_score: float
    runner_up_score: float
    margin: float
    proposed_canonical: str | None
    candidates: tuple[dict, ...]

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe review-task payload (``task_type='ambiguous_er'``) (§16.5)."""
        return {
            "task_type": "ambiguous_er",
            "candidate_id": self.candidate_id,
            "mentions": list(self.mentions),
            "top_score": self.top_score,
            "runner_up_score": self.runner_up_score,
            "margin": self.margin,
            "proposed_canonical": self.proposed_canonical,
            "candidates": [dict(c) for c in self.candidates],
        }


def _match_prob(match: Mapping[str, Any]) -> float:
    """Read ``match_probability`` from an ER match, defaulting to ``0.0`` (§16.5)."""
    try:
        return float(match.get("match_probability", 0.0))
    except (TypeError, ValueError):
        return 0.0


def detect_ambiguous(
    candidate: Mapping[str, Any],
    *,
    margin_threshold: float = 0.1,
) -> AmbiguousErFinding | None:
    """Return an :class:`AmbiguousErFinding` for *candidate*, or ``None`` (§16.5).

    Reads a Splink-style ER output: ``{candidate_id, mentions, matches:[{entity_id,
    match_probability}], decision?}``. A finding is emitted when the ER
    ``decision == 'review_needed'`` OR when the sorted top-1 minus top-2
    ``match_probability`` is ``< margin_threshold``. Otherwise returns ``None``.
    A cluster with fewer than two matches has no runner-up ambiguity, so — unless
    the ER explicitly asks for review — it yields ``None``.
    """
    matches = list(candidate.get("matches") or [])
    matches_sorted = sorted(matches, key=_match_prob, reverse=True)

    decision = candidate.get("decision")
    review_requested = decision == "review_needed"

    top_score = _match_prob(matches_sorted[0]) if matches_sorted else 0.0
    runner_up_score = _match_prob(matches_sorted[1]) if len(matches_sorted) > 1 else 0.0
    has_runner_up = len(matches_sorted) > 1
    margin = top_score - runner_up_score

    close_margin = has_runner_up and margin < margin_threshold
    if not (review_requested or close_margin):
        return None

    mentions = tuple(str(m) for m in (candidate.get("mentions") or []))
    proposed_canonical: str | None = None
    if matches_sorted:
        entity_id = matches_sorted[0].get("entity_id")
        proposed_canonical = None if entity_id is None else str(entity_id)

    return AmbiguousErFinding(
        candidate_id=str(candidate.get("candidate_id", "")),
        mentions=mentions,
        top_score=top_score,
        runner_up_score=runner_up_score,
        margin=margin,
        proposed_canonical=proposed_canonical,
        candidates=tuple(dict(m) for m in matches_sorted),
    )


def scan(
    candidates: Sequence[Mapping[str, Any]],
    *,
    margin_threshold: float = 0.1,
) -> list[AmbiguousErFinding]:
    """Scan *candidates*, returning one finding per ambiguous cluster (§16.5)."""
    findings: list[AmbiguousErFinding] = []
    for candidate in candidates:
        finding = detect_ambiguous(candidate, margin_threshold=margin_threshold)
        if finding is not None:
            findings.append(finding)
    return findings
