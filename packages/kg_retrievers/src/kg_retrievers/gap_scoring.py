"""Gap priority scoring + ranking (§15.9).

The gap scanner (:mod:`kg_retrievers.gap_analysis`, §15) materializes many
``Gap`` nodes; §15.9 asks the system to *explain and rank* them so a curator or
the agent layer can act on the few that matter most. This module turns a raw
gap dict into a single priority score in ``[0, 1]`` and a short Russian (RU)
explanation of *why* the gap is worth closing.

The score is a convex combination (weighted average, so it stays in ``[0, 1]``)
of four signals, each itself in ``[0, 1]``:

- **absence_confidence** — уверенность в отсутствии: how sure we are the value is
  truly missing rather than merely un-extracted (§25.11). Higher → more worth
  flagging.
- **importance** — важность/центральность субъекта: how central the subject is
  (a passed-in graph-centrality score, or a neutral default).
- **domain_criticality** — критичность предметной области: some domains (water
  treatment, desalination) are more mission-critical than others (§24).
- **novelty** — новизна/актуальность: a fresh, not-yet-revisited gap outranks a
  stale one (falls back to the ``recency`` key, then to neutral).

Pure python — no graph or store access; callers assemble the gap dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The four scored signals, in a fixed order (§15.9).
COMPONENT_NAMES: tuple[str, ...] = (
    "absence_confidence",
    "importance",
    "domain_criticality",
    "novelty",
)

# Default signal weights (§15.9). Absence-confidence dominates because a gap we
# are unsure is real is not worth a curator's time; the four sum to 1.0 so the
# default score is already a plain weighted average.
DEFAULT_WEIGHTS: dict[str, float] = {
    "absence_confidence": 0.40,
    "importance": 0.25,
    "domain_criticality": 0.20,
    "novelty": 0.15,
}

# Per-domain criticality prior in [0,1] (§24). Keyed by lowercased domain label;
# both EN and RU spellings resolve to the same weight. Unknown/empty → neutral.
DOMAIN_CRITICALITY: dict[str, float] = {
    "water_treatment": 1.0,
    "водоподготовка": 1.0,
    "desalination": 0.95,
    "опреснение": 0.95,
    "membrane": 0.9,
    "мембраны": 0.9,
    "materials": 0.8,
    "материалы": 0.8,
    "energy": 0.7,
    "энергетика": 0.7,
    "general": 0.5,
    "общее": 0.5,
}
DEFAULT_DOMAIN_CRITICALITY: float = 0.5
DEFAULT_SIGNAL: float = 0.5  # neutral value for any missing numeric signal


def _clamp01(x: float) -> float:
    """Clamp ``x`` into the closed unit interval ``[0, 1]``."""
    return max(0.0, min(1.0, float(x)))


def _num(value: object, default: float) -> float:
    """Read a numeric signal in ``[0, 1]``; non-numbers (and bools) → ``default``."""
    if isinstance(value, bool):  # bool is an int subclass — treat as "not a score"
        return default
    if isinstance(value, (int, float)):
        return _clamp01(float(value))
    return default


def domain_criticality_score(domain: object) -> float:
    """Criticality прайор in ``[0, 1]`` for a domain label (unknown/empty → neutral)."""
    if not isinstance(domain, str) or not domain.strip():
        return DEFAULT_DOMAIN_CRITICALITY
    return DOMAIN_CRITICALITY.get(domain.strip().lower(), DEFAULT_DOMAIN_CRITICALITY)


def _subject(gap: dict) -> str:
    """Best human label for the gap's subject (material/entity), RU fallback."""
    for key in ("subject", "material", "name", "entity"):
        value = gap.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "объект"


def _property(gap: dict) -> str:
    """Best label for the missing property, RU fallback."""
    for key in ("property", "property_name"):
        value = gap.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "целевое свойство"


def gap_score_components(gap: dict) -> dict[str, float]:
    """Resolve the four ``[0, 1]`` signals from a gap dict, applying defaults (§15.9)."""
    novelty = gap.get("novelty")
    if novelty is None:
        novelty = gap.get("recency")
    return {
        "absence_confidence": _num(gap.get("absence_confidence"), DEFAULT_SIGNAL),
        "importance": _num(gap.get("importance"), DEFAULT_SIGNAL),
        "domain_criticality": domain_criticality_score(gap.get("domain")),
        "novelty": _num(novelty, DEFAULT_SIGNAL),
    }


def _combine(components: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted average of the four signals, normalized by weight sum → ``[0, 1]``."""
    total_w = sum(max(0.0, weights.get(name, 0.0)) for name in COMPONENT_NAMES)
    if total_w <= 0.0:  # degenerate all-zero weights → nothing to prioritize on
        return 0.0
    score = sum(max(0.0, weights.get(name, 0.0)) * components[name] for name in COMPONENT_NAMES)
    return round(score / total_w, 4)


def gap_priority_score(gap: dict, *, weights: dict[str, float] | None = None) -> float:
    """Priority of a gap in ``[0, 1]`` (higher → close it sooner) per §15.9.

    Combines absence-confidence, subject importance, domain criticality and
    novelty as a weighted average. ``weights`` overrides :data:`DEFAULT_WEIGHTS`
    (missing keys count as 0); the result is renormalized by the weight sum so it
    always lands in ``[0, 1]``. Missing gap fields fall back to neutral defaults.
    """
    return _combine(gap_score_components(gap), weights or DEFAULT_WEIGHTS)


def _priority_word(score: float) -> str:
    """RU priority band label for an explanation string."""
    if score >= 0.66:
        return "Высокий"
    if score >= 0.33:
        return "Средний"
    return "Низкий"


def gap_explanation(gap: dict, *, weights: dict[str, float] | None = None) -> str:
    """One short RU sentence explaining why the gap matters (§15.9)."""
    comps = gap_score_components(gap)
    score = _combine(comps, weights or DEFAULT_WEIGHTS)
    gap_type = str(gap.get("gap_type") or "неизвестный тип")
    reasons = (
        f"уверенность в отсутствии {comps['absence_confidence']:.2f}, "
        f"важность субъекта {comps['importance']:.2f}, "
        f"критичность области {comps['domain_criticality']:.2f}, "
        f"новизна {comps['novelty']:.2f}"
    )
    return (
        f"{_priority_word(score)} приоритет пробела «{gap_type}» для «{_subject(gap)}»: {reasons}."
    )


def next_experiment_hint(gap: dict) -> str:
    """One-line RU experiment suggestion that closes the gap (§15.9).

    Mentions the subject (material/entity) and, when known, the property and
    domain, e.g. ``Провести эксперимент: <material> × <property> в области <domain>``.
    """
    subject = _subject(gap)
    prop = _property(gap)
    domain = gap.get("domain")
    domain_part = f" в области «{domain}»" if isinstance(domain, str) and domain.strip() else ""
    return f"Провести эксперимент: {subject} × {prop}{domain_part}."


@dataclass(frozen=True)
class ScoredGap:
    """A gap enriched with its priority score, RU explanation and next step (§15.9)."""

    gap_type: str
    subject: str
    domain: str | None
    score: float
    explanation: str
    hint: str
    components: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "gap_type": self.gap_type,
            "subject": self.subject,
            "domain": self.domain,
            "score": self.score,
            "explanation": self.explanation,
            "hint": self.hint,
            "components": dict(self.components),
        }


def score_gap(gap: dict, *, weights: dict[str, float] | None = None) -> ScoredGap:
    """Build a :class:`ScoredGap` (score + RU explanation + hint) from a gap dict (§15.9)."""
    w = weights or DEFAULT_WEIGHTS
    comps = gap_score_components(gap)
    domain = gap.get("domain")
    return ScoredGap(
        gap_type=str(gap.get("gap_type") or "неизвестный тип"),
        subject=_subject(gap),
        domain=domain if isinstance(domain, str) and domain.strip() else None,
        score=_combine(comps, w),
        explanation=gap_explanation(gap, weights=w),
        hint=next_experiment_hint(gap),
        components=comps,
    )


def rank_gaps(gaps: list[dict], *, weights: dict[str, float] | None = None) -> list[ScoredGap]:
    """Score every gap and return them ranked by priority, descending (§15.9).

    Ties keep their original relative order (stable sort), so the ranking is
    deterministic for equal-priority gaps.
    """
    scored = [score_gap(gap, weights=weights) for gap in gaps]
    scored.sort(key=lambda sg: sg.score, reverse=True)
    return scored
