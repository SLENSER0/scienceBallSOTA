"""Auto-generation of review tasks from extraction signals (§16.5).

The review queue (очередь проверки) should not be filled by hand: the same
signals the router already computes — low confidence (низкая уверенность) and
quality flags (флаги качества) — are enough to *mint* a review task for a
curator. This module turns raw extraction items into de-duplicated
:class:`ReviewTaskSpec` records, reusing :func:`review_routing.route_extraction`
(§6.15) as the single source of truth for the *review vs auto-accept* decision.

Policy (§16.5):

* an item is routed through :func:`route_extraction`; **only** items whose
  verdict is ``review`` become tasks — ``auto_accept`` (автопринятие) and
  ``reject`` (отклонение) produce nothing;
* the task ``kind`` splits by *why* review was demanded — an escalation flag
  (нет единицы / вне диапазона / конфликт / OCR) yields ``flag_review``, a bare
  mid-confidence band yields ``confidence_review``;
* ``reason`` carries the router's ordered reason tokens; ``priority`` is the
  router's queue priority verbatim (приоритет), so the shakiest facts sort first;
* tasks are de-duplicated on ``dedup_key = f"{target_id}:{kind}"`` — one open
  task per target per kind — keeping the highest-priority representative.

Separately, :func:`new_schema_term_task` mints a ``schema_change`` task from an
*unknown-property* signal (неизвестное свойство, §12.1): when an extractor meets
a property/term absent from the controlled vocabulary, a curator must decide
whether to extend the schema. Pure Python — no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_extractors.review_routing import (
    ACTION_REVIEW,
    Item,
    ReviewDecision,
    route_extraction,
)

# --- task kinds (виды задач проверки, §16.5) ----------------------------------
KIND_CONFIDENCE_REVIEW = "confidence_review"  # mid-confidence band (§6.15)
KIND_FLAG_REVIEW = "flag_review"  # escalation flag raised (§6.15)
KIND_SCHEMA_CHANGE = "schema_change"  # unknown property/term (§12.1)

#: Fallback target id when an item carries no identifier (нет идентификатора).
_UNKNOWN_TARGET = "unknown"
#: Item keys read, in order, to identify a task's target (§16.5).
_TARGET_KEYS: tuple[str, ...] = ("target_id", "id")
#: Fixed queue priority for a schema-term task — sorts near the top (§12.1).
SCHEMA_TERM_PRIORITY = 0.9
#: Decimals kept when rounding priority (stable, hand-checkable values).
_PRIORITY_DECIMALS = 6


@dataclass(frozen=True)
class ReviewTaskSpec:
    """One review task minted from an extraction signal (§16.5).

    Fields
    ------
    target_id
        Identifier of the reviewed thing (fact / entity / term).
    kind
        Task category — :data:`KIND_CONFIDENCE_REVIEW`,
        :data:`KIND_FLAG_REVIEW` or :data:`KIND_SCHEMA_CHANGE`.
    priority
        Review-queue priority (приоритет); higher = look sooner. Copied from the
        router for extraction tasks, fixed for schema-term tasks.
    reason
        Human-readable explanation — the router's reason tokens joined, or a
        schema-term prompt.
    dedup_key
        Stable de-dup key ``f"{target_id}:{kind}"`` — one open task per target
        per kind.
    """

    target_id: str
    kind: str
    priority: float
    reason: str
    dedup_key: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, JSON-friendly)."""
        return {
            "target_id": self.target_id,
            "kind": self.kind,
            "priority": self.priority,
            "reason": self.reason,
            "dedup_key": self.dedup_key,
        }


def _dedup_key(target_id: str, kind: str) -> str:
    """Stable de-dup key for a task: ``f"{target_id}:{kind}"`` (§16.5)."""
    return f"{target_id}:{kind}"


def _make_spec(target_id: str, kind: str, priority: float, reason: str) -> ReviewTaskSpec:
    """Assemble a :class:`ReviewTaskSpec`, deriving ``dedup_key`` from id + kind."""
    return ReviewTaskSpec(
        target_id=target_id,
        kind=kind,
        priority=round(float(priority), _PRIORITY_DECIMALS),
        reason=reason,
        dedup_key=_dedup_key(target_id, kind),
    )


def _target_id(item: Item) -> str:
    """Read a target id from *item* (``target_id`` then ``id``); fallback token."""
    for key in _TARGET_KEYS:
        raw = item.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return _UNKNOWN_TARGET


def _spec_from_decision(item: Item, decision: ReviewDecision) -> ReviewTaskSpec:
    """Build a review task for *item* from its router *decision* (§16.5).

    Escalated verdicts (flag-driven) become :data:`KIND_FLAG_REVIEW`; a bare
    mid-confidence verdict becomes :data:`KIND_CONFIDENCE_REVIEW`. The reason is
    the router's ordered reason tokens; the priority is copied verbatim.
    """
    kind = KIND_FLAG_REVIEW if decision.escalated else KIND_CONFIDENCE_REVIEW
    reason = ", ".join(decision.reasons) if decision.reasons else kind
    return _make_spec(_target_id(item), kind, decision.priority, reason)


def generate_review_tasks(
    items: list[Item],
    *,
    thresholds: dict[str, float] | None = None,
) -> list[ReviewTaskSpec]:
    """Mint de-duplicated review tasks from extraction *items* (§16.5).

    Each item is routed through :func:`route_extraction` (§6.15); **only** items
    whose verdict is ``review`` yield a task — ``auto_accept`` and ``reject``
    yield nothing. Tasks sharing a ``dedup_key`` (``target_id:kind``) collapse to
    the highest-priority one, and the result is ordered by descending priority so
    the shakiest facts head the queue (ties keep first-seen order). An empty input
    yields ``[]``.
    """
    kept: dict[str, tuple[int, ReviewTaskSpec]] = {}
    for idx, item in enumerate(items):
        decision = route_extraction(item, thresholds=thresholds)
        if decision.action != ACTION_REVIEW:
            continue
        spec = _spec_from_decision(item, decision)
        prev = kept.get(spec.dedup_key)
        if prev is None:
            kept[spec.dedup_key] = (idx, spec)
        elif spec.priority > prev[1].priority:
            # Keep the first-seen index for a stable order; take the urgent spec.
            kept[spec.dedup_key] = (prev[0], spec)

    ordered = sorted(kept.values(), key=lambda pair: (-pair[1].priority, pair[0]))
    return [spec for _, spec in ordered]


def new_schema_term_task(term: str) -> ReviewTaskSpec:
    """Mint a ``schema_change`` task from an unknown-property signal (§12.1).

    When an extractor meets a property/term (свойство/термин) outside the
    controlled vocabulary, a curator must decide whether to extend the schema.
    The *term* is the task target, so its ``dedup_key`` is ``f"{term}:schema_change"``
    — repeated sightings collapse to one task. Priority is fixed at
    :data:`SCHEMA_TERM_PRIORITY`. A blank *term* is rejected.
    """
    name = str(term).strip()
    if not name:
        raise ValueError("term must be a non-empty schema term (§12.1)")
    reason = f"unknown schema term '{name}' — propose vocabulary addition (§12.1)"
    return _make_spec(name, KIND_SCHEMA_CHANGE, SCHEMA_TERM_PRIORITY, reason)
