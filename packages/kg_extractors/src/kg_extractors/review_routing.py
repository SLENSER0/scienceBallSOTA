"""Extraction review routing — route low-confidence facts to a curator (§6.15).

Every extracted fact carries a ``confidence`` (показатель уверенности) plus,
optionally, quality ``flags`` raised upstream (unit gate §7.5, span validator
§6.10, conflict/merge §6.13, OCR §5). This module folds those signals into one
:class:`ReviewDecision` — *auto-accept* (автопринятие), *review* (ручная
проверка) or *reject* (отклонение) — and a queue ``priority`` (приоритет) so a
curator sees the shakiest facts first.

Routing policy (§6.15):

* ``confidence >= auto_accept_at`` → **auto_accept** (only for clean items);
* ``confidence < reject_at``      → **reject** (only for clean items);
* otherwise                       → **review**;
* *any* escalation reason forces **review**, overriding the confidence band —
  a flagged fact is never silently accepted *or* dropped, a human must look.

Escalation reasons (причины эскалации) are read from the item:

* ``missing_unit`` — a numeric ``value`` with no ``unit`` (нет единицы, §7.5);
* ``out_of_range`` — value outside physical bounds (вне диапазона, §7.7);
* ``conflicting``  — extractors disagree on this fact (конфликт, §6.13);
* ``low_ocr``      — sourced from low-quality OCR (низкое качество OCR, §5).

``priority`` grows as confidence falls (``1 - confidence``) and gets a small
bump per escalation, so low-confidence and flagged facts sort to the top of the
review queue. Pure Python — no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: One extraction item: ``{confidence, flags?, unit?, value?, ...}`` (§6.15).
Item = dict[str, object]

# --- routing actions (§6.15) --------------------------------------------------
ACTION_AUTO_ACCEPT = "auto_accept"
ACTION_REVIEW = "review"
ACTION_REJECT = "reject"

VALID_ACTIONS: frozenset[str] = frozenset({ACTION_AUTO_ACCEPT, ACTION_REVIEW, ACTION_REJECT})

# --- escalation reason / flag tokens (§6.15) ----------------------------------
REASON_MISSING_UNIT = "missing_unit"  # нет единицы (§7.5)
REASON_OUT_OF_RANGE = "out_of_range"  # вне диапазона (§7.7)
REASON_CONFLICTING = "conflicting"  # конфликт извлечений (§6.13)
REASON_LOW_OCR = "low_ocr"  # низкое качество OCR (§5)
# confidence-band reasons (explain a non-auto-accept driven purely by score).
REASON_LOW_CONFIDENCE = "low_confidence"  # < reject_at (низкая уверенность)
REASON_MID_CONFIDENCE = "mid_confidence"  # review band (средняя уверенность)

#: Escalation tokens that, present in ``flags``, force manual review (§6.15).
_ESCALATION_FLAGS: tuple[str, ...] = (
    REASON_MISSING_UNIT,
    REASON_OUT_OF_RANGE,
    REASON_CONFLICTING,
    REASON_LOW_OCR,
)

#: Default routing thresholds (пороги маршрутизации, §6.15).
DEFAULT_THRESHOLDS: dict[str, float] = {"auto_accept_at": 0.85, "reject_at": 0.2}

#: Priority bump added per escalation reason (флаги двигают вверх очередь).
_ESCALATION_WEIGHT = 0.05
#: Decimals kept when rounding priority (stable, hand-checkable values).
_PRIORITY_DECIMALS = 6


@dataclass(frozen=True)
class ReviewDecision:
    """Routing verdict for one extraction item (§6.15).

    Fields
    ------
    action
        One of ``auto_accept`` / ``review`` / ``reject`` (:data:`VALID_ACTIONS`).
    reasons
        Ordered, de-duplicated reason tokens explaining the verdict — escalation
        tokens first, then a confidence-band token (empty for a clean
        auto-accept).
    priority
        Review-queue priority (приоритет); higher = look sooner. Grows as
        confidence falls and with each escalation reason.
    """

    action: str
    priority: float
    reasons: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        """True when a curator must inspect this fact (``review``)."""
        return self.action == ACTION_REVIEW

    @property
    def escalated(self) -> bool:
        """True when an escalation reason (not just score) drove the verdict."""
        return any(r in _ESCALATION_FLAGS for r in self.reasons)

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, JSON-friendly)."""
        return {
            "action": self.action,
            "priority": self.priority,
            "reasons": list(self.reasons),
            "needs_review": self.needs_review,
            "escalated": self.escalated,
        }


@dataclass(frozen=True)
class BatchRouting:
    """Bucketed routing over many items — lists + counts (§6.15).

    ``auto_accept`` and ``reject`` preserve input order; ``review`` is sorted by
    descending priority so the shakiest facts head the curator's queue.
    """

    auto_accept: list[Item] = field(default_factory=list)
    review: list[Item] = field(default_factory=list)
    reject: list[Item] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total number of routed items (buckets partition the input)."""
        return len(self.auto_accept) + len(self.review) + len(self.reject)

    def as_dict(self) -> dict[str, object]:
        """Full structured view (buckets + counts + total)."""
        return {
            "auto_accept": list(self.auto_accept),
            "review": list(self.review),
            "reject": list(self.reject),
            "counts": dict(self.counts),
            "total": self.total,
        }


def _to_float(value: object, default: float = 0.0) -> float:
    """Coerce *value* to ``float`` (comma decimals allowed); *default* on failure."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return default
    return default


def _clamp01(value: float) -> float:
    """Clamp *value* into the ``[0, 1]`` confidence interval (§6.15)."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _unit_missing(unit: object) -> bool:
    """True when *unit* is absent or blank (нет единицы, §7.5)."""
    return unit is None or not str(unit).strip()


def _escalation_reasons(item: Item) -> list[str]:
    """Collect escalation reasons for *item*, canonically ordered + de-duped (§6.15).

    Reads the item's ``flags`` list (``out_of_range`` / ``conflicting`` /
    ``low_ocr`` / ``missing_unit``) and *derives* ``missing_unit`` when the item
    carries a numeric ``value`` but no ``unit`` (a measurement without units).
    """
    raw = item.get("flags") or []
    flagset = {str(f).strip().lower() for f in raw}

    # Derive missing_unit for a value-bearing item lacking a unit (§7.5).
    if item.get("value") is not None and _unit_missing(item.get("unit")):
        flagset.add(REASON_MISSING_UNIT)

    return [flag for flag in _ESCALATION_FLAGS if flag in flagset]


def route_extraction(
    item: Item,
    *,
    thresholds: dict[str, float] | None = None,
) -> ReviewDecision:
    """Route one extraction *item* to auto-accept / review / reject (§6.15).

    The confidence band (``auto_accept_at`` / ``reject_at``, defaulting to
    :data:`DEFAULT_THRESHOLDS` and overridable per call) proposes an action; any
    escalation reason (:func:`_escalation_reasons`) forces ``review`` instead, so
    a flagged fact is never auto-accepted *or* rejected. ``priority`` rises as
    confidence falls and with each escalation.

    Examples (hand-checked): ``{"confidence": 0.9}`` → auto_accept;
    ``{"confidence": 0.1}`` → reject; ``{"confidence": 0.5}`` → review;
    ``{"confidence": 0.95, "flags": ["out_of_range"]}`` → review.
    """
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    auto_at = float(t["auto_accept_at"])
    reject_at = float(t["reject_at"])

    conf = _clamp01(_to_float(item.get("confidence")))
    escalations = _escalation_reasons(item)
    reasons: list[str] = list(escalations)

    if conf >= auto_at:
        band = ACTION_AUTO_ACCEPT
    elif conf < reject_at:
        band = ACTION_REJECT
        reasons.append(REASON_LOW_CONFIDENCE)
    else:
        band = ACTION_REVIEW
        reasons.append(REASON_MID_CONFIDENCE)

    # Escalation flags override the score band → always manual review (§6.15).
    action = ACTION_REVIEW if escalations else band

    priority = round((1.0 - conf) + _ESCALATION_WEIGHT * len(escalations), _PRIORITY_DECIMALS)
    return ReviewDecision(action=action, priority=priority, reasons=reasons)


def route_batch(
    items: list[Item],
    *,
    thresholds: dict[str, float] | None = None,
) -> BatchRouting:
    """Route many *items*, bucketing them by action with counts (§6.15).

    Returns a :class:`BatchRouting` whose three buckets partition *items* (so the
    counts always sum to ``len(items)``). The ``review`` bucket is ordered by
    descending priority — the lowest-confidence / most-flagged facts first.
    """
    auto_accept: list[Item] = []
    reject: list[Item] = []
    scored_review: list[tuple[float, int, Item]] = []

    for idx, item in enumerate(items):
        decision = route_extraction(item, thresholds=thresholds)
        if decision.action == ACTION_AUTO_ACCEPT:
            auto_accept.append(item)
        elif decision.action == ACTION_REJECT:
            reject.append(item)
        else:
            # Keep idx as a stable tiebreaker; never compares the dict itself.
            scored_review.append((decision.priority, idx, item))

    scored_review.sort(key=lambda row: (-row[0], row[1]))
    review = [item for _, _, item in scored_review]

    counts = {
        ACTION_AUTO_ACCEPT: len(auto_accept),
        ACTION_REVIEW: len(review),
        ACTION_REJECT: len(reject),
    }
    return BatchRouting(
        auto_accept=auto_accept,
        review=review,
        reject=reject,
        counts=counts,
    )
