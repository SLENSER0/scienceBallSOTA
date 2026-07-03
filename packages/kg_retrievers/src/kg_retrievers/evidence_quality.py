"""§12.6 — evidence-quality scoring done right (span / source_type / review_status).

Оценка качества эвиденса (*evidence quality*) в диапазоне ``[0, 1]``. В отличие от
:func:`kg_retrievers.scoring.evidence_quality_score` (spec-exact companion, который
учитывает только силу провенанса и уверенность), функция
:func:`evidence_quality_v2` дополнительно вознаграждает те сигналы, которые аудит
нашёл проигнорированными:

* **span** — наличие точной локации в источнике (символьный диапазон
  ``char_start``/``char_end`` **или** ячейка таблицы ``row``/``col``) строго
  повышает балл: попадание *со* span всегда выше идентичного попадания *без* span;
* **source_type** — упорядочение носителя факта: ``table_cell`` > ``paragraph`` >
  ``figure_caption`` > ``metadata`` (табличная ячейка надёжнее подписи к рисунку);
* **review_status** — верификация (``accepted``/``verified``/``corrected`` или
  ``verified=True``) повышает балл, а отклонение (``rejected``) обнуляет его
  (~0.0) независимо от силы эвиденса.

English: :func:`evidence_quality_v2` combines *evidence_strength × confidence* (the
core signal, as in :mod:`kg_retrievers.scoring`) with three previously-ignored
modifiers via a convex combination whose weights sum to 1.0 — so the result is
always in ``[0, 1]`` and strictly monotone in each modifier. A ``rejected`` hit
short-circuits to ``~0.0`` regardless of every other field.

Pure Python, deterministic, offline-safe (no LLM, no store access) — callers pass a
plain evidence dict. Kuzu note: an Evidence node's ``char_start``/``char_end``/
``row``/``col``/``source_type``/``review_status`` are custom props, not queryable
columns; read them via :meth:`KuzuGraphStore.get_node` before calling this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Силы провенанса (§3.6). Mirrors ``scoring.STRENGTH_RANK`` for independence. ──
# Higher = stronger provenance. Unknown / missing strengths fall back to 0.3.
STRENGTH_RANK: dict[str, float] = {
    "peer_reviewed": 1.0,
    "patent": 0.8,
    "experiment_protocol": 0.75,
    "standard": 0.7,
    "internal_report": 0.55,
    "conference": 0.5,
    "preprint": 0.45,
    "unverified": 0.3,
}
DEFAULT_STRENGTH: float = 0.3

# Упорядочение носителя факта (§12.6): table_cell > paragraph > figure_caption >
# metadata. Unknown / missing source types fall back to a sane middle value.
SOURCE_TYPE_RANK: dict[str, float] = {
    "table_cell": 1.0,
    "paragraph": 0.7,
    "figure_caption": 0.4,
    "metadata": 0.15,
}
DEFAULT_SOURCE_SCORE: float = 0.5

# Статусы ревью (§3.15). Verified boosts to the top; pending/unknown stay neutral;
# rejected short-circuits the whole score to ``REJECTED_SCORE``.
VERIFIED_STATUSES: frozenset[str] = frozenset({"accepted", "verified", "corrected"})
REJECTED_STATUSES: frozenset[str] = frozenset({"rejected"})
VERIFIED_SCORE: float = 1.0
NEUTRAL_REVIEW_SCORE: float = 0.5
REJECTED_SCORE: float = 0.0

DEFAULT_CONFIDENCE: float = 0.6

# Ключи символьного span и ячейки таблицы (§11.11). Char-span & table-cell keys.
_CHAR_START_KEYS: tuple[str, ...] = ("char_start", "span_start")
_CHAR_END_KEYS: tuple[str, ...] = ("char_end", "span_end")
_ROW_KEYS: tuple[str, ...] = ("row", "table_row", "cell_row")
_COL_KEYS: tuple[str, ...] = ("col", "column", "table_col", "cell_col")


@dataclass(frozen=True)
class QualityWeights:
    """Веса выпуклой комбинации (§12.6). Convex-combination weights (must sum to 1)."""

    core: float = 0.40  # evidence_strength × confidence
    source: float = 0.20  # source_type ordering
    span: float = 0.20  # source-span presence
    verified: float = 0.20  # review_status verification

    def __post_init__(self) -> None:
        total = self.core + self.source + self.span + self.verified
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"QualityWeights must sum to 1.0, got {total}")

    def as_dict(self) -> dict[str, float]:
        """Serialise to a plain JSON-ready dict."""
        return {
            "core": self.core,
            "source": self.source,
            "span": self.span,
            "verified": self.verified,
        }


# Единственный экземпляр весов по умолчанию (§12.6). Shared default weights.
WEIGHTS = QualityWeights()


@dataclass(frozen=True)
class QualityBreakdown:
    """Разложение балла качества эвиденса (§12.6). Auditable quality breakdown.

    Attributes:
        strength: сила провенанса в ``[0, 1]`` (``evidence_strength`` → rank).
        confidence: уверенность в ``[0, 1]`` (clamped).
        core: ядро сигнала ``strength × confidence``.
        source_type_score: балл носителя факта в ``[0, 1]``.
        span_present: есть ли точная локация (span или ячейка таблицы).
        span_score: ``1.0`` при наличии span, иначе ``0.0``.
        verified_score: ``1.0`` verified / ``0.5`` pending / (rejected → 0.0).
        rejected: отклонён ли эвиденс (``review_status``/``rejected``).
        review_status: нормализованный статус ревью (lower-case) или ``""``.
        score: итоговый балл качества в ``[0, 1]``.
    """

    strength: float
    confidence: float
    core: float
    source_type_score: float
    span_present: bool
    span_score: float
    verified_score: float
    rejected: bool
    review_status: str
    score: float
    weights: dict[str, float] = field(default_factory=lambda: WEIGHTS.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict."""
        return {
            "strength": self.strength,
            "confidence": self.confidence,
            "core": self.core,
            "source_type_score": self.source_type_score,
            "span_present": self.span_present,
            "span_score": self.span_score,
            "verified_score": self.verified_score,
            "rejected": self.rejected,
            "review_status": self.review_status,
            "score": self.score,
            "weights": dict(self.weights),
        }


def _as_offset(value: Any) -> int | None:
    """Coerce a stored offset (int / numeric str) to a non-negative ``int`` or ``None``.

    ``bool`` is rejected (it is an ``int`` subclass) and ``0`` is a valid offset —
    presence is tested against ``None``, never truthiness.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _first_offset(ev: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """First key in ``keys`` whose value coerces to a non-negative offset, else ``None``."""
    for key in keys:
        got = _as_offset(ev.get(key))
        if got is not None:
            return got
    return None


def has_span(ev: dict[str, Any]) -> bool:
    """True iff the evidence carries a precise source location (§12.6 / §11.11).

    A char span (``char_start`` **and** ``char_end``) or a table cell (a ``row``
    **and** a ``col``) both count; either alone (only start, only row, …) does not.
    """
    if _first_offset(ev, _CHAR_START_KEYS) is not None and (
        _first_offset(ev, _CHAR_END_KEYS) is not None
    ):
        return True
    row = _first_offset(ev, _ROW_KEYS)
    col = _first_offset(ev, _COL_KEYS)
    return row is not None and col is not None


def _strength_score(ev: dict[str, Any]) -> float:
    """Provenance strength in ``[0, 1]`` (unknown / missing → ``DEFAULT_STRENGTH``)."""
    key = str(ev.get("evidence_strength") or "").strip().lower()
    return STRENGTH_RANK.get(key, DEFAULT_STRENGTH)


def _confidence_score(ev: dict[str, Any]) -> float:
    """Confidence clamped to ``[0, 1]`` (non-numeric / missing → ``DEFAULT_CONFIDENCE``)."""
    conf = ev.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return DEFAULT_CONFIDENCE
    return max(0.0, min(1.0, float(conf)))


def _source_type_score(ev: dict[str, Any]) -> float:
    """Source-type rank in ``[0, 1]`` (unknown / missing → ``DEFAULT_SOURCE_SCORE``)."""
    key = str(ev.get("source_type") or "").strip().lower()
    return SOURCE_TYPE_RANK.get(key, DEFAULT_SOURCE_SCORE)


def _review_status(ev: dict[str, Any]) -> str:
    """Normalised (lower-case, trimmed) review status, or ``""`` when absent."""
    return str(ev.get("review_status") or "").strip().lower()


def _is_rejected(ev: dict[str, Any], status: str) -> bool:
    """True iff the evidence is rejected (``review_status`` or a ``rejected`` flag)."""
    return status in REJECTED_STATUSES or ev.get("rejected") is True


def _is_verified(ev: dict[str, Any], status: str) -> bool:
    """True iff the evidence is verified (``review_status`` or a ``verified`` flag)."""
    return status in VERIFIED_STATUSES or ev.get("verified") is True


def evidence_quality_breakdown(
    ev: dict[str, Any], *, weights: QualityWeights = WEIGHTS
) -> QualityBreakdown:
    """Full, auditable §12.6 quality breakdown for one evidence dict.

    ``score`` is the convex combination
    ``w.core·(strength·conf) + w.source·source + w.span·span + w.verified·verified``
    — always in ``[0, 1]`` — unless the evidence is ``rejected``, in which case the
    score short-circuits to ``REJECTED_SCORE`` (~0.0) regardless of every other field.
    """
    strength = _strength_score(ev)
    confidence = _confidence_score(ev)
    core = strength * confidence
    source = _source_type_score(ev)
    span_present = has_span(ev)
    span = 1.0 if span_present else 0.0
    status = _review_status(ev)
    rejected = _is_rejected(ev, status)
    verified = VERIFIED_SCORE if _is_verified(ev, status) else NEUTRAL_REVIEW_SCORE

    if rejected:
        verified = REJECTED_SCORE
        score = REJECTED_SCORE
    else:
        raw = (
            weights.core * core
            + weights.source * source
            + weights.span * span
            + weights.verified * verified
        )
        score = round(max(0.0, min(1.0, raw)), 4)

    return QualityBreakdown(
        strength=round(strength, 4),
        confidence=round(confidence, 4),
        core=round(core, 4),
        source_type_score=round(source, 4),
        span_present=span_present,
        span_score=span,
        verified_score=verified,
        rejected=rejected,
        review_status=status,
        score=score,
        weights=weights.as_dict(),
    )


def evidence_quality_v2(ev: dict[str, Any], *, weights: QualityWeights = WEIGHTS) -> float:
    """Evidence quality in ``[0, 1]`` combining strength × confidence with span,
    source-type ordering and review status (§12.6).

    Monotone guarantees (all else equal): a hit **with** a source span scores
    strictly higher than one **without**; ``table_cell`` > ``paragraph`` >
    ``figure_caption`` > ``metadata``; ``verified`` > pending; a ``rejected`` hit
    scores ``~0.0`` regardless of strength. Missing fields default sanely.
    """
    return evidence_quality_breakdown(ev, weights=weights).score
