"""§25.13 — self-check roll-up of annotated absence gaps.

§25.13 annotates every suspected пробел (gap) with an absence verdict
(``present`` / ``covered`` / ``retracted`` / ``possible_miss`` / ``genuine_gap``
/ ``abstain``) and a per-gap P(extractor missed). Before those annotations reach
the query-graph summary, this module folds them into one compact
:class:`AbsenceSelfCheck`: how many gaps landed in each verdict bucket, and a
plain-language warning for every gap that carries a high пропуск-извлечения
(extraction-miss) risk — either because its verdict is ``possible_miss`` or
because its ``p_extractor_missed`` reaches :data:`HIGH_MISS_AT`.

The roll-up is a pure function of its input list. Each item may be an
:class:`~kg_retrievers.absence_annotate.AnnotatedGap` (or any attribute-bearing
object) or a plain ``dict``; :func:`summarize_absence` reads ``verdict``,
``p_extractor_missed`` and a label/id field from either shape. Read-only: it
issues no graph queries, so the Kuzu note (custom node props are not queryable
columns) never comes into play here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# High extractor-miss risk threshold: at or above this P(extractor missed) a gap
# earns a self-check warning regardless of its verdict (§25.13).
HIGH_MISS_AT = 0.60

# Verdict vocabulary (§25.11) — mirrored here so the roll-up needs no store.
PRESENT = "present"
COVERED = "covered"
RETRACTED = "retracted"
POSSIBLE_MISS = "possible_miss"
GENUINE_GAP = "genuine_gap"
ABSTAIN = "abstain"

# Fields consulted, in order, for a human-readable gap label.
_LABEL_KEYS = ("gap_id", "label", "id", "material_id", "name")


@dataclass(frozen=True)
class AbsenceSelfCheck:
    """Roll-up of §25.13 absence verdicts for the query-graph summary.

    Counts are non-negative and sum to ``total``. ``high_miss_warnings`` holds
    one RU/EN warning string per gap flagged for high extraction-miss risk
    (verdict ``possible_miss`` or ``p_extractor_missed >= HIGH_MISS_AT``).
    """

    n_genuine_gap: int
    n_possible_miss: int
    n_retracted: int
    n_abstain: int
    n_present: int
    total: int
    high_miss_warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_genuine_gap": self.n_genuine_gap,
            "n_possible_miss": self.n_possible_miss,
            "n_retracted": self.n_retracted,
            "n_abstain": self.n_abstain,
            "n_present": self.n_present,
            "total": self.total,
            "high_miss_warnings": list(self.high_miss_warnings),
        }


def _read(gap: Any, key: str) -> Any:
    """Read ``key`` from a gap given as a mapping or an attribute-bearing object."""
    if isinstance(gap, Mapping):
        return gap.get(key)
    return getattr(gap, key, None)


def _label_of(gap: Any) -> str:
    """First non-empty label/id field for a gap, or a stable ``<gap>`` fallback."""
    for key in _LABEL_KEYS:
        value = _read(gap, key)
        if value:
            return str(value)
    return "<gap>"


def _miss_prob(gap: Any) -> float:
    """P(extractor missed) for a gap; a missing/None value reads as ``0.0``."""
    raw = _read(gap, "p_extractor_missed")
    return 0.0 if raw is None else float(raw)


def summarize_absence(annotated: list) -> AbsenceSelfCheck:
    """Fold annotated absence gaps into a §25.13 :class:`AbsenceSelfCheck`.

    ``annotated`` is a list of gaps, each an
    :class:`~kg_retrievers.absence_annotate.AnnotatedGap` (or object) or a dict
    exposing ``verdict``, ``p_extractor_missed`` and a label/id field. Counts the
    ``genuine_gap`` / ``possible_miss`` / ``retracted`` / ``abstain`` /
    ``present`` verdicts (``covered`` folds into ``present``, the downgraded
    bucket), and emits one warning per gap whose verdict is ``possible_miss`` or
    whose ``p_extractor_missed`` reaches :data:`HIGH_MISS_AT`. Pure and
    read-only; an empty input yields all-zero counts and no warnings.
    """
    counts = {
        GENUINE_GAP: 0,
        POSSIBLE_MISS: 0,
        RETRACTED: 0,
        ABSTAIN: 0,
        PRESENT: 0,
    }
    warnings: list[str] = []
    for gap in annotated:
        verdict = _read(gap, "verdict")
        p_miss = _miss_prob(gap)
        if verdict == COVERED:
            verdict = PRESENT  # covered is a downgraded, present-like verdict
        if verdict in counts:
            counts[verdict] += 1
        if verdict == POSSIBLE_MISS or p_miss >= HIGH_MISS_AT:
            warnings.append(
                f"Высокий риск пропуска извлечения / high extractor-miss risk: "
                f"{_label_of(gap)} (verdict={verdict}, p_extractor_missed={p_miss:.2f})"
            )
    return AbsenceSelfCheck(
        n_genuine_gap=counts[GENUINE_GAP],
        n_possible_miss=counts[POSSIBLE_MISS],
        n_retracted=counts[RETRACTED],
        n_abstain=counts[ABSTAIN],
        n_present=counts[PRESENT],
        total=len(annotated),
        high_miss_warnings=warnings,
    )
