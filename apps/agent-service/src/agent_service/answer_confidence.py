"""§13.17 агрегация итоговой уверенности ответа / overall answer confidence.

The §5.3 :class:`AnswerPayload` carries a ``confidence`` field and
``answer_assembler.py`` (§13.14) accepts it as an *input*, but nothing in the run
state actually *computes* it. This module fills that gap: it folds the per-evidence
confidences, the open gaps and the detected contradictions into a single clamped
score, and — when a verifier ran — caps that score by the verifier's ceiling.

The maths is deterministic and pure-python (no graph store, no LLM), so it is
trivially unit-testable:

* ``base`` — среднее уверенностей доказательств / mean of evidence ``confidence``
  values (``0.0`` when there is no evidence);
* ``gap_penalty`` — ``gap_step * len(gaps)`` вычитается за каждый пробел;
* ``contradiction_penalty`` — ``contradiction_step * len(contradictions)``;
* the raw score ``base - gap_penalty - contradiction_penalty`` is clamped to
  ``[0.0, 1.0]`` (штрафы никогда не уводят ниже нуля / penalties never go negative);
* if ``verifier_cap`` is given the clamped score is finally lowered to
  ``min(score, verifier_cap)`` — верификатор задаёт потолок / a verifier ceiling.

:class:`ConfidenceBreakdown` keeps every intermediate term so callers can render or
log *why* a score came out the way it did; :meth:`ConfidenceBreakdown.as_dict`
renders an orjson-safe plain dict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Разбор итоговой уверенности / the aggregated answer-confidence breakdown.

    Every field is a plain float (``verifier_cap`` is ``None`` when no verifier ran),
    so the dataclass is immutable and JSON-ready. ``score`` is the final value after
    clamping and the optional verifier cap; the other fields explain how it was
    reached (base plus the two subtracted penalties).
    """

    base: float
    gap_penalty: float
    contradiction_penalty: float
    verifier_cap: float | None
    score: float

    def as_dict(self) -> dict[str, Any]:
        """Plain orjson-safe dict со всеми пятью полями / all five fields as a dict."""
        return {
            "base": self.base,
            "gap_penalty": self.gap_penalty,
            "contradiction_penalty": self.contradiction_penalty,
            "verifier_cap": self.verifier_cap,
            "score": self.score,
        }


def _mean_confidence(evidence: Sequence[Mapping[str, Any]]) -> float:
    """Среднее поля ``confidence`` / mean of the evidence ``confidence`` values.

    Missing ``confidence`` keys count as ``0.0``; an empty sequence yields ``0.0``
    (нет доказательств → нулевая база / no evidence means a zero base).
    """
    if not evidence:
        return 0.0
    total = sum(float(item.get("confidence", 0.0)) for item in evidence)
    return total / len(evidence)


def compute_answer_confidence(
    evidence: list[dict],
    gaps: list[dict],
    contradictions: list[dict],
    verifier_cap: float | None = None,
    *,
    gap_step: float = 0.05,
    contradiction_step: float = 0.1,
) -> ConfidenceBreakdown:
    """Свести уверенность ответа в один балл / aggregate answer confidence to a score.

    ``base`` is the mean of the evidence ``confidence`` values (``0.0`` if empty).
    Each open gap subtracts ``gap_step`` and each contradiction subtracts
    ``contradiction_step``; the difference is clamped to ``[0.0, 1.0]`` so penalties
    never push the score below zero. When ``verifier_cap`` is not ``None`` the clamped
    score is finally lowered to ``min(score, verifier_cap)`` (потолок верификатора).

    :param evidence: evidence dicts, each with an optional ``confidence`` float.
    :param gaps: open information gaps; only the count matters here.
    :param contradictions: detected contradictions; only the count matters here.
    :param verifier_cap: optional upper bound imposed by a verifier stage.
    :param gap_step: penalty subtracted per gap (default ``0.05``).
    :param contradiction_step: penalty subtracted per contradiction (default ``0.1``).
    :returns: a :class:`ConfidenceBreakdown` carrying base, penalties, cap and score.
    """
    base = _mean_confidence(evidence)
    gap_penalty = gap_step * len(gaps)
    contradiction_penalty = contradiction_step * len(contradictions)

    raw = base - gap_penalty - contradiction_penalty
    score = min(1.0, max(0.0, raw))
    if verifier_cap is not None:
        score = min(score, verifier_cap)

    return ConfidenceBreakdown(
        base=base,
        gap_penalty=gap_penalty,
        contradiction_penalty=contradiction_penalty,
        verifier_cap=verifier_cap,
        score=score,
    )
