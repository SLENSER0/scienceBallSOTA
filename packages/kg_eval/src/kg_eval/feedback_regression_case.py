"""Domain-expert feedback → frozen regression cases (§23.22).

Domain expert validation loop: when a domain expert flags an answer as wrong,
that feedback is frozen into a deterministic ``RegressionCase`` so the exact
failure never silently regresses. Each case pins ``expected_substrings`` that a
correct answer must contain and ``forbidden_substrings`` that it must never
contain again.

Петля валидации экспертом (§23.22): обратная связь эксперта замораживается в
детерминированный регрессионный кейс. ``case_id`` выводится из вопроса и типа
события (sha256), поэтому один и тот же дефект даёт один и тот же id и легко
дедуплицируется. Kuzu-примечание: кастомные свойства узла не являются колонками
для RETURN — это чистые in-memory dataclass'ы, к стору не привязаны.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_CATEGORY_MISSING_EVIDENCE = "evidence_required"
_CATEGORY_WRONG_NUMBER = "numeric_accuracy"
_CATEGORY_DEFAULT = "general"


def _case_id(question: str, fb_type: str) -> str:
    """Deterministic 'reg-' + first 12 hex chars of sha256(question + type)."""
    digest = hashlib.sha256((question + fb_type).encode("utf-8")).hexdigest()
    return "reg-" + digest[:12]


@dataclass(frozen=True)
class RegressionCase:
    """A frozen regression case distilled from one expert feedback event.

    ``expected_substrings`` must all appear in a correct answer;
    ``forbidden_substrings`` must never appear. ``case_id`` is deterministic
    (see :func:`_case_id`) so identical defects collapse to one id.
    """

    case_id: str
    question: str
    expected_substrings: tuple[str, ...]
    forbidden_substrings: tuple[str, ...]
    category: str
    source_feedback_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "expected_substrings": list(self.expected_substrings),
            "forbidden_substrings": list(self.forbidden_substrings),
            "category": self.category,
            "source_feedback_id": self.source_feedback_id,
        }


def from_feedback(fb: Mapping[str, object]) -> RegressionCase:
    """Map a FeedbackEvent mapping to a :class:`RegressionCase`.

    ``type == 'wrong_number'``: ``forbidden`` gets the wrong value string and
    ``expected`` gets ``fb['correct_value']``. ``type == 'missing_evidence'``:
    ``category == 'evidence_required'`` and ``forbidden`` stays empty.
    """
    fb_type = str(fb.get("type", ""))
    question = str(fb.get("question", ""))
    source_feedback_id = str(fb.get("id", ""))

    expected: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()

    if fb_type == "wrong_number":
        category = _CATEGORY_WRONG_NUMBER
        forbidden = (str(fb["wrong_value"]),)
        expected = (str(fb["correct_value"]),)
    elif fb_type == "missing_evidence":
        category = _CATEGORY_MISSING_EVIDENCE
        if "expected_evidence" in fb:
            expected = (str(fb["expected_evidence"]),)
    else:
        category = _CATEGORY_DEFAULT

    return RegressionCase(
        case_id=_case_id(question, fb_type),
        question=question,
        expected_substrings=expected,
        forbidden_substrings=forbidden,
        category=category,
        source_feedback_id=source_feedback_id,
    )


def dedup(cases: Sequence[RegressionCase]) -> tuple[RegressionCase, ...]:
    """Drop duplicate ``case_id`` (keeping first), return sorted by ``case_id``."""
    seen: dict[str, RegressionCase] = {}
    for case in cases:
        if case.case_id not in seen:
            seen[case.case_id] = case
    return tuple(sorted(seen.values(), key=lambda c: c.case_id))
