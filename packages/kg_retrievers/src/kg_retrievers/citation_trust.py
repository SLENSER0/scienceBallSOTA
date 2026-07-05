"""Citation-level source trust / retraction / freshness fusion (§23.27).

The individual signals already ship as pure modules but were never *surfaced*
together on a finished answer:

* :mod:`kg_common.source_freshness` classifies *staleness* (fresh/aging/stale);
* :mod:`kg_common.source_trust_score` folds freshness + retraction + peer-review
  + citations into one ``0..1`` trust score and tier;
* :mod:`kg_retrievers.retractions` / ``trust_weighted_support`` know *whether* a
  source was withdrawn.

This module fuses them **per citation** and rolls the result up into an
answer-level verdict that the API and UI need for §23.27 acceptance:

* every citation gets a :class:`CitationTrust` — its trust score, tier, freshness
  level and the human-readable warnings it carries («отозван / устарел /
  непроверен»);
* the answer gets an :class:`AnswerTrustReport` — the aggregated, de-duplicated
  warnings and, crucially, a **verifier confidence penalty**: a base confidence
  is multiplied down once per triggered warning category, harder when the
  offending source is a *primary* support (retracted evidence must never be the
  main support without a warning, §23.27).

Everything here is a pure, deterministic function over plain mappings — no store,
no wall-clock, no LLM — so it is trivially testable and hand-checkable. Callers
(the router) look up the raw per-source metadata and hand it in.

Public API:

* :data:`SOURCE_STATUSES`   — the recognised ``source_status`` values.
* :class:`CitationTrust`    — frozen per-citation verdict with ``as_dict``.
* :class:`AnswerTrustReport` — frozen answer-level roll-up with ``as_dict``.
* :func:`assess_citation`   — verdict for one citation mapping.
* :func:`assess_answer`     — roll-up over an answer's citations + confidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from kg_common.source_freshness import classify
from kg_common.source_trust_score import score_source

__all__ = [
    "SOURCE_STATUSES",
    "CitationTrust",
    "AnswerTrustReport",
    "assess_citation",
    "assess_answer",
]

# --------------------------------------------------------------------------- #
# Source-status vocabulary (§23.27) — статусы источника                        #
# --------------------------------------------------------------------------- #

#: Recognised ``source_status`` values — active/corrected/retracted/superseded/deprecated.
SOURCE_STATUSES: tuple[str, ...] = (
    "active",
    "corrected",
    "retracted",
    "superseded",
    "deprecated",
)

#: Statuses that withdraw a source outright — trust short-circuits to 0 (§23.27).
_RETRACTED_STATUSES: frozenset[str] = frozenset({"retracted", "superseded"})

#: A soft-degraded status: not withdrawn, but trust is scaled down.
_DEPRECATED_STATUS = "deprecated"

#: Multiplier applied to the trust score of a ``deprecated`` (but live) source.
_DEPRECATED_TRUST_SCALE = 0.6

# --------------------------------------------------------------------------- #
# Warning catalogue — каталог предупреждений («отозван / устарел / непроверен»)#
# --------------------------------------------------------------------------- #

# code -> (severity, russian message, per-category confidence penalty when the
# offending citation is a *primary* support). Non-primary hits are softened
# (half the reduction) so the answer is dinged less for a merely-cited source.
_WARNINGS: dict[str, tuple[str, str, float]] = {
    "retracted": ("critical", "источник отозван (retracted)", 0.35),
    "superseded": ("critical", "источник заменён более новым (superseded)", 0.5),
    "deprecated": ("high", "источник устарел и не поддерживается (deprecated)", 0.8),
    "stale": ("high", "данные источника устарели (нет свежих обновлений)", 0.85),
    "unreviewed": ("medium", "источник не прошёл рецензирование / проверку", 0.92),
}

#: Severity rank for ordering the aggregate — critical worst.
_SEVERITY_RANK: dict[str, int] = {"critical": 3, "high": 2, "medium": 1, "none": 0}

# A fixed as-of clock so freshness classification is fully deterministic: we
# reconstruct a synthetic ``last_ingest_at`` from the supplied ``age_days`` and
# reuse the shipped :func:`kg_common.source_freshness.classify` thresholds
# (fresh <= 30d, stale > 180d).
_AS_OF = datetime(2000, 1, 1, tzinfo=UTC)


def _freshness_level(
    doc_id: str, age_days: float | None, *, fresh_days: int = 30, stale_days: int = 180
) -> str:
    """Freshness level for a source via the shipped classifier (§10.7).

    ``fresh_days``/``stale_days`` default to the ingest-recency thresholds (30/180d).
    Callers scoring *publication* age (annual granularity) must pass year-scaled
    thresholds, else every paper older than ~6 months is misclassified ``stale``.
    """
    if age_days is None:
        return classify(doc_id, None, _AS_OF).level
    last = _AS_OF - timedelta(days=float(age_days))
    return classify(doc_id, last, _AS_OF, fresh_days=fresh_days, stale_days=stale_days).level


# --------------------------------------------------------------------------- #
# Per-citation verdict                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CitationTrust:
    """Trust / freshness / retraction verdict for one citation (§23.27).

    ``doc_id`` identifies the source; ``source_status`` is its normalised status;
    ``trust_score``/``trust_tier`` come from :func:`kg_common.source_trust_score.score_source`
    (a retracted/superseded source scores ``0.0`` / tier ``untrusted``, a
    ``deprecated`` one is scaled down); ``freshness_level`` is fresh/aging/stale/
    unknown; ``primary`` marks a main support; ``warnings`` are the triggered
    warning codes; ``warning_messages`` their RU texts.
    """

    doc_id: str
    source_status: str
    trust_score: float
    trust_tier: str
    freshness_level: str
    age_days: float | None
    primary: bool
    warnings: tuple[str, ...]
    warning_messages: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "source_status": self.source_status,
            "trust_score": round(self.trust_score, 6),
            "trust_tier": self.trust_tier,
            "freshness_level": self.freshness_level,
            "age_days": self.age_days,
            "primary": self.primary,
            "warnings": list(self.warnings),
            "warning_messages": list(self.warning_messages),
        }


def _normalize_status(raw: object) -> str:
    """Coerce an arbitrary ``source_status`` to a known value (default active)."""
    status = str(raw or "active").strip().lower()
    return status if status in SOURCE_STATUSES else "active"


def assess_citation(
    citation: Mapping[str, object], *, fresh_days: int = 30, stale_days: int = 180
) -> CitationTrust:
    """Fuse trust + freshness + retraction for one citation (§23.27).

    Reads ``doc_id`` (or ``source_id``), ``source_status`` (default ``active``),
    ``age_days`` (``None`` → unknown freshness), ``peer_reviewed`` (default
    ``False``), ``citation_count`` (default ``0``) and ``primary`` (default
    ``False``) from the mapping. Delegates scoring to the shipped
    ``source_trust_score`` and freshness ``classify``; a ``deprecated`` source
    keeps a live-but-scaled trust, a retracted/superseded one short-circuits to
    ``untrusted``. Returns the per-citation :class:`CitationTrust` with any
    triggered warnings.
    """
    doc_id = str(citation.get("doc_id") or citation.get("source_id") or "")
    status = _normalize_status(citation.get("source_status"))
    age_raw = citation.get("age_days")
    age_days = None if age_raw is None else float(age_raw)  # type: ignore[arg-type]
    peer_reviewed = bool(citation.get("peer_reviewed", False))
    citation_count = int(citation.get("citation_count", 0) or 0)
    primary = bool(citation.get("primary", False))

    retracted = status in _RETRACTED_STATUSES
    verdict = score_source(
        source_id=doc_id,
        age_days=abs(age_days) if age_days is not None else 0.0,
        retracted=retracted,
        peer_reviewed=peer_reviewed,
        citation_count=citation_count,
    )
    trust_score = verdict.score
    trust_tier = verdict.tier
    if status == _DEPRECATED_STATUS and not retracted:
        trust_score = round(trust_score * _DEPRECATED_TRUST_SCALE, 6)
        trust_tier = "low" if trust_score < 0.34 else trust_tier

    freshness_level = _freshness_level(
        doc_id, age_days, fresh_days=fresh_days, stale_days=stale_days
    )

    warnings: list[str] = []
    if status == "retracted":
        warnings.append("retracted")
    elif status == "superseded":
        warnings.append("superseded")
    elif status == "deprecated":
        warnings.append("deprecated")
    if freshness_level == "stale":
        warnings.append("stale")
    if not peer_reviewed:
        warnings.append("unreviewed")

    messages = tuple(_WARNINGS[code][1] for code in warnings)
    return CitationTrust(
        doc_id=doc_id,
        source_status=status,
        trust_score=trust_score,
        trust_tier=trust_tier,
        freshness_level=freshness_level,
        age_days=age_days,
        primary=primary,
        warnings=tuple(warnings),
        warning_messages=messages,
    )


# --------------------------------------------------------------------------- #
# Answer-level roll-up + verifier confidence penalty                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AnswerTrustReport:
    """Answer-level trust roll-up with a verifier confidence penalty (§23.27).

    ``citations`` are the per-citation verdicts. ``warnings`` is the
    de-duplicated, severity-ordered list of ``{code, severity, message, doc_ids,
    primary}`` aggregates. ``base_confidence`` is the verifier's confidence
    *before* trust adjustment; ``adjusted_confidence`` is *after* (never larger);
    ``confidence_penalty`` is their ratio. ``min_trust`` is the lowest citation
    trust; ``severity`` the worst warning severity (or ``none``).
    """

    citations: tuple[CitationTrust, ...]
    warnings: tuple[dict[str, object], ...]
    has_warnings: bool
    severity: str
    base_confidence: float
    adjusted_confidence: float
    confidence_penalty: float
    min_trust: float
    relies_on_retracted: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "citations": [c.as_dict() for c in self.citations],
            "warnings": [dict(w) for w in self.warnings],
            "has_warnings": self.has_warnings,
            "severity": self.severity,
            "base_confidence": round(self.base_confidence, 6),
            "adjusted_confidence": round(self.adjusted_confidence, 6),
            "confidence_penalty": round(self.confidence_penalty, 6),
            "min_trust": round(self.min_trust, 6),
            "relies_on_retracted": self.relies_on_retracted,
        }


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def assess_answer(
    citations: Sequence[Mapping[str, object]],
    *,
    base_confidence: float = 1.0,
) -> AnswerTrustReport:
    """Roll citation verdicts into an answer report + confidence penalty (§23.27).

    Each citation is scored via :func:`assess_citation`. For every *distinct*
    triggered warning category the verifier confidence is multiplied by that
    category's penalty (from the warning catalogue); a hit on a **primary**
    support applies the full penalty, a hit only on non-primary citations applies
    a *softened* penalty (half the reduction). This is the §23.27 «verifier
    снижает confidence» behaviour and it makes a *retracted primary* source hurt
    the most. The result confidence is clamped to ``[0, 1]`` and never exceeds
    ``base_confidence``.

    Warnings are de-duplicated by code, tagged with severity and the offending
    ``doc_ids``, and ordered worst-severity first. An empty citation list yields a
    clean report (no warnings, confidence unchanged).
    """
    verdicts = tuple(assess_citation(c) for c in citations)

    # Group the offending doc_ids per warning code, tracking whether any hit was
    # on a primary support.
    grouped: dict[str, dict[str, object]] = {}
    primary_hit: dict[str, bool] = {}
    for v in verdicts:
        for code in v.warnings:
            entry = grouped.setdefault(
                code,
                {
                    "code": code,
                    "severity": _WARNINGS[code][0],
                    "message": _WARNINGS[code][1],
                    "doc_ids": [],
                    "primary": False,
                },
            )
            docs = entry["doc_ids"]
            assert isinstance(docs, list)
            if v.doc_id and v.doc_id not in docs:
                docs.append(v.doc_id)
            if v.primary:
                entry["primary"] = True
                primary_hit[code] = True

    # Verifier confidence penalty: one multiplicative factor per triggered code.
    penalty = 1.0
    for code in grouped:
        full = _WARNINGS[code][2]
        # Full penalty on a primary support; halve the reduction otherwise.
        factor = full if primary_hit.get(code) else 1.0 - (1.0 - full) / 2.0
        penalty *= factor

    base = _clamp01(float(base_confidence))
    adjusted = _clamp01(base * penalty)

    warnings = tuple(
        sorted(
            grouped.values(),
            key=lambda w: (-_SEVERITY_RANK[str(w["severity"])], str(w["code"])),
        )
    )
    severity = "none"
    for w in warnings:
        sev = str(w["severity"])
        if _SEVERITY_RANK[sev] > _SEVERITY_RANK[severity]:
            severity = sev

    trusts = [v.trust_score for v in verdicts]
    min_trust = min(trusts) if trusts else 1.0
    relies_on_retracted = any(
        v.primary and v.source_status in _RETRACTED_STATUSES for v in verdicts
    )

    return AnswerTrustReport(
        citations=verdicts,
        warnings=warnings,
        has_warnings=bool(warnings),
        severity=severity,
        base_confidence=base,
        adjusted_confidence=adjusted,
        confidence_penalty=penalty,
        min_trust=min_trust,
        relies_on_retracted=relies_on_retracted,
    )
