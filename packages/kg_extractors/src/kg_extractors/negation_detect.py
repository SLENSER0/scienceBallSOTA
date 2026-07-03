"""Evidence-span rule — no-span-no-fact negation & absence detection (§6.10).

``span_validator`` guards against hallucinated evidence spans, but a *validated*
span may still assert a **negated** or **absent** statement — "no significant
increase", "not observed", "absence of precipitates". Turning such a sentence
into a *positive* graph fact is a semantic error the span check cannot catch.

This module scans a snippet for a small vocabulary of negation / absence
triggers and reports whether the statement is negated, which trigger fired, and
the text scope the negation governs (the substring from the trigger onward).
:func:`is_positive_fact` is the inverse gate a fact-builder consults before
emitting an edge: a positive fact must *not* be negated.

Правило доказательной цитаты: детекция отрицания/отсутствия (§6.10).

Pure python — no dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Negation / absence triggers (§6.10). Lower-cased; matched case-insensitively.
# Order is not significant: detection picks the earliest occurrence in the text,
# breaking ties toward the longest trigger.
NEGATION_TRIGGERS: tuple[str, ...] = (
    "no significant",
    "not observed",
    "did not",
    "without",
    "absence of",
    "no change",
)


@dataclass(frozen=True)
class NegationResult:
    """Outcome of a negation scan over one snippet (§6.10)."""

    negated: bool
    trigger: str | None
    scope_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "negated": bool(self.negated),
            "trigger": self.trigger,
            "scope_text": self.scope_text,
        }


def detect_negation(text: str) -> NegationResult:
    """Scan *text* for a negation/absence trigger (§6.10).

    Matches :data:`NEGATION_TRIGGERS` case-insensitively. When one or more fire,
    the earliest occurrence wins (ties broken toward the longest trigger); the
    returned :class:`NegationResult` is ``negated=True`` with the matched trigger
    (in its canonical lower-cased form) and ``scope_text`` set to the original
    substring from the trigger onward. With no trigger, returns
    ``negated=False``, ``trigger=None`` and an empty ``scope_text``.
    """
    lowered = text.lower()
    best_index: int | None = None
    best_trigger: str | None = None
    for trigger in NEGATION_TRIGGERS:
        index = lowered.find(trigger)
        if index == -1:
            continue
        if (
            best_index is None
            or index < best_index
            or (index == best_index and len(trigger) > len(best_trigger or ""))
        ):
            best_index = index
            best_trigger = trigger
    if best_index is None or best_trigger is None:
        return NegationResult(negated=False, trigger=None, scope_text="")
    return NegationResult(
        negated=True,
        trigger=best_trigger,
        scope_text=text[best_index:],
    )


def is_positive_fact(text: str) -> bool:
    """True iff *text* is a positive (non-negated) statement (§6.10)."""
    return not detect_negation(text).negated
