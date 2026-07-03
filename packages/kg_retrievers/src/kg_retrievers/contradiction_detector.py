"""Richer measurement-contradiction heuristics (§15.4).

Расширенное выявление противоречий — pure-python analysis over two *normalized*
Measurement dicts that goes **beyond plain numeric divergence** (§15.4). Given two
measurements of the same property, it decides whether they contradict and, if so,
by which mechanism:

- ``numeric_divergence`` — same unit and the relative difference of the point
  values ``|a-b| / max(|a|,|b|) >= 0.30`` (расхождение значений);
- ``ci_disjoint`` — the reported confidence intervals do not overlap, even when
  the point estimates look close (непересекающиеся доверительные интервалы);
- ``effect_direction`` — the qualitative effect points opposite ways, e.g. one
  source reports ``increase`` and the other ``decrease`` (противоположный эффект).

Each input is a plain dict with ``value_normalized`` / ``normalized_unit`` and the
optional keys ``evidence_strength`` / ``confidence`` / ``ci_low`` / ``ci_high`` /
``effect_direction``. The module is pure and side-effect free — it never touches
the graph store. Results are frozen dataclasses exposing ``as_dict()`` for JSON
transport. Missing or malformed fields degrade gracefully (no error, ``none``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "ContradictionVerdict",
    "classify_pair",
    "detect_contradiction",
    "DIVERGENCE_THRESHOLD",
    "EVIDENCE_RANK",
]

# A normalized Measurement dict; only ``value_normalized`` is usually present.
Measurement = dict[str, Any]

# One triggered heuristic: (subtype, severity in [0,1], human-readable reason).
Finding = tuple[str, float, str]

# §15.4 relative-divergence threshold (mirrors ``gap_analysis.DIVERGENCE``).
DIVERGENCE_THRESHOLD = 0.30

# Provenance-strength ordering (§3.6): peer_reviewed > patent > internal_report >
# unverified. Unknown / missing strengths rank below every known one (default 0).
EVIDENCE_RANK: dict[str, int] = {
    "peer_reviewed": 6,
    "patent": 5,
    "experiment_protocol": 4,
    "standard": 4,
    "internal_report": 3,
    "expert_comment": 2,
    "unverified": 1,
}

# Contradiction subtypes, strongest first — used to pick the *primary* subtype
# when several rules fire on one pair: a qualitative direction flip beats disjoint
# CIs, which beat a mere point divergence (§15.4).
SUBTYPE_PRIORITY: dict[str, int] = {
    "effect_direction": 3,
    "ci_disjoint": 2,
    "numeric_divergence": 1,
    "none": 0,
}

# Effect-direction synonyms → canonical {'increase', 'decrease', 'none'} (§15.4).
_INCREASE = frozenset({"increase", "increases", "increased", "up", "positive", "rise", "+"})
_DECREASE = frozenset({"decrease", "decreases", "decreased", "down", "negative", "fall", "-"})
_NEUTRAL = frozenset({"none", "no_effect", "neutral", "flat", "unchanged"})


@dataclass(frozen=True)
class ContradictionVerdict:
    """Verdict on whether two measurements contradict (§15.4).

    ``subtype`` is one of ``numeric_divergence`` / ``ci_disjoint`` /
    ``effect_direction`` / ``none``. ``severity`` is the strength of the primary
    finding in ``[0, 1]``. ``likely_correct`` names the stronger-evidence side
    (``'a'`` / ``'b'``), decided by ``evidence_strength`` then ``confidence``, or
    ``None`` when neither wins. ``reasons`` lists every triggered heuristic,
    strongest first (доводы).
    """

    is_contradiction: bool
    subtype: str
    severity: float
    likely_correct: str | None
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "is_contradiction": self.is_contradiction,
            "subtype": self.subtype,
            "severity": self.severity,
            "likely_correct": self.likely_correct,
            "reasons": list(self.reasons),
        }


def _as_float(value: Any) -> float | None:
    """Coerce ``value`` to ``float`` (``bool`` and non-numerics → ``None``)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _same_unit(a: Measurement, b: Measurement) -> bool:
    """True when the two measurements share a unit (both unit-less counts too)."""
    ua, ub = a.get("normalized_unit"), b.get("normalized_unit")
    if ua is None and ub is None:
        return True
    return ua == ub


def _normalize_direction(value: Any) -> str | None:
    """Map an effect-direction token to ``increase`` / ``decrease`` / ``none``."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    if key in _INCREASE:
        return "increase"
    if key in _DECREASE:
        return "decrease"
    if key in _NEUTRAL:
        return "none"
    return None


def _numeric_finding(a: Measurement, b: Measurement) -> Finding | None:
    """Flag same-unit point values diverging by ``>= DIVERGENCE_THRESHOLD``."""
    if not _same_unit(a, b):
        return None
    va, vb = _as_float(a.get("value_normalized")), _as_float(b.get("value_normalized"))
    if va is None or vb is None:
        return None
    scale = max(abs(va), abs(vb))
    if scale == 0.0:
        return None
    rel = abs(va - vb) / scale
    if rel < DIVERGENCE_THRESHOLD:
        return None
    unit = a.get("normalized_unit") or b.get("normalized_unit") or ""
    suffix = f" {unit}" if unit else ""
    reason = (
        f"relative divergence {rel:.2f} >= {DIVERGENCE_THRESHOLD:.2f} "
        f"(a={va:g}{suffix}, b={vb:g}{suffix})"
    )
    return ("numeric_divergence", min(1.0, rel), reason)


def _ci_finding(a: Measurement, b: Measurement) -> Finding | None:
    """Flag non-overlapping confidence intervals (disjoint even if means close)."""
    if not _same_unit(a, b):
        return None
    a_lo, a_hi = _as_float(a.get("ci_low")), _as_float(a.get("ci_high"))
    b_lo, b_hi = _as_float(b.get("ci_low")), _as_float(b.get("ci_high"))
    if a_lo is None or a_hi is None or b_lo is None or b_hi is None:
        return None
    # Normalize each interval so low <= high (tolerate swapped bounds).
    a_lo, a_hi = min(a_lo, a_hi), max(a_lo, a_hi)
    b_lo, b_hi = min(b_lo, b_hi), max(b_lo, b_hi)
    gap = max(b_lo - a_hi, a_lo - b_hi)
    if gap <= 0.0:  # overlapping or merely touching → not disjoint
        return None
    span = (a_hi - a_lo) + (b_hi - b_lo)
    severity = gap / (gap + span) if (gap + span) > 0.0 else 1.0
    severity = min(1.0, max(0.0, severity))
    reason = f"disjoint CIs [{a_lo:g},{a_hi:g}] vs [{b_lo:g},{b_hi:g}] (gap {gap:g})"
    return ("ci_disjoint", severity, reason)


def _direction_finding(a: Measurement, b: Measurement) -> Finding | None:
    """Flag an opposite qualitative effect (``increase`` vs ``decrease``)."""
    da = _normalize_direction(a.get("effect_direction"))
    db = _normalize_direction(b.get("effect_direction"))
    if da is None or db is None:
        return None
    if {da, db} == {"increase", "decrease"}:
        return ("effect_direction", 1.0, f"opposite effect direction ({da} vs {db})")
    return None


def classify_pair(a: Measurement, b: Measurement) -> list[Finding]:
    """Return every triggered contradiction finding, strongest first (§15.4).

    A helper over the three heuristics — direction flip, disjoint CIs, numeric
    divergence — sorted by subtype priority then severity so ``findings[0]`` is
    the primary finding. An empty list means the pair agrees / is unconstrained.
    """
    findings: list[Finding] = []
    for finding in (_direction_finding(a, b), _ci_finding(a, b), _numeric_finding(a, b)):
        if finding is not None:
            findings.append(finding)
    findings.sort(key=lambda f: (SUBTYPE_PRIORITY[f[0]], f[1]), reverse=True)
    return findings


def _likely_correct(a: Measurement, b: Measurement) -> str | None:
    """Pick the stronger side by ``evidence_strength`` then ``confidence``."""
    ra = EVIDENCE_RANK.get(str(a.get("evidence_strength") or "").lower(), 0)
    rb = EVIDENCE_RANK.get(str(b.get("evidence_strength") or "").lower(), 0)
    if ra != rb:
        return "a" if ra > rb else "b"
    ca, cb = _as_float(a.get("confidence")), _as_float(b.get("confidence"))
    if ca is not None and cb is not None and ca != cb:
        return "a" if ca > cb else "b"
    return None


def detect_contradiction(a: Measurement, b: Measurement) -> ContradictionVerdict:
    """Decide whether measurements ``a`` and ``b`` contradict (§15.4).

    Runs all heuristics via :func:`classify_pair`; the highest-priority finding
    sets ``subtype`` and ``severity``, and ``likely_correct`` names the
    stronger-evidence side. When nothing fires the verdict is a graceful
    ``none`` with ``severity=0.0`` and ``likely_correct=None``.
    """
    findings = classify_pair(a, b)
    if not findings:
        return ContradictionVerdict(
            is_contradiction=False,
            subtype="none",
            severity=0.0,
            likely_correct=None,
            reasons=(),
        )
    subtype, severity, _reason = findings[0]
    return ContradictionVerdict(
        is_contradiction=True,
        subtype=subtype,
        severity=round(severity, 4),
        likely_correct=_likely_correct(a, b),
        reasons=tuple(f[2] for f in findings),
    )
