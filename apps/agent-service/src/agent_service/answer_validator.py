"""§13.12 валидация ответа / answer validation (pure python).

A post-synthesis sanity check that never touches the graph store: given the
rendered ``answer`` text and the list of citations attached to it, flag numeric
claims (числовые утверждения) that carry no inline citation marker ``[n]`` in
their sentence. A number backed by a nearby marker is treated as grounded; the
rest surface in :attr:`AnswerValidation.numeric_claims_without_evidence`, so an
unsupported «твёрдость 9» or «45%» cannot slip through uncited.

Deterministic and dependency-free — see :mod:`agent_service.citation_formatter`
for the ``[n]`` marker convention and :mod:`agent_service.verifier` for the
graph-backed grounding check this complements. The check is sentence-scoped: a
citation marker anywhere in a number's sentence grounds every number in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Inline citation marker, e.g. ``[1]`` / ``[12]`` — one or more digits in brackets.
_MARKER_RE = re.compile(r"\[\d+\]")

# A numeric-claim token: integer/decimal (``.`` or ``,`` grouped) with an optional
# trailing ``%``. The leading guard keeps the "2" in "H2O" or a year suffix from
# matching mid-word — a claim must start at a non-word, non-dot boundary.
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*%?")

# Sentence boundary: whitespace after a terminator, or a run of newlines. The
# lookbehind never fires inside a decimal ("1.2" — the dot precedes a digit, not
# whitespace), so numbers stay intact.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class AnswerValidation:
    """Result of §13.12 numeric-claim validation over a rendered answer.

    ``ok`` is ``True`` when no numeric claim is left without evidence.
    ``numeric_claims_without_evidence`` lists the offending number tokens in order
    of appearance (в порядке появления), ``has_citations`` mirrors whether any
    citation is attached, and ``issues`` holds RU/EN human-readable notes.
    """

    ok: bool
    numeric_claims_without_evidence: list[str]
    has_citations: bool
    issues: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{ok, numeric_claims_without_evidence, has_citations, issues}``."""
        return {
            "ok": self.ok,
            "numeric_claims_without_evidence": list(self.numeric_claims_without_evidence),
            "has_citations": self.has_citations,
            "issues": list(self.issues),
        }


def _sentences(text: str) -> list[str]:
    """Split ``text`` into non-empty, stripped sentences (пустые строки отброшены)."""
    return [s for s in (part.strip() for part in _SENTENCE_SPLIT_RE.split(text)) if s]


def validate_answer(answer: str, citations: list[Any]) -> AnswerValidation:
    """Flag numeric claims in ``answer`` that lack an inline ``[n]`` citation (§13.12).

    ``answer`` is split into sentences; a number token is grounded when its sentence
    carries at least one inline marker ``[n]`` **and** ``citations`` is non-empty
    (без цитат — заземлять нечем / with no citations there is nothing to ground on).
    Ungrounded numbers, in order of appearance, land in
    ``numeric_claims_without_evidence`` and ``ok`` is ``True`` iff that list is empty.
    Markers themselves are never counted as claims (``[1]`` — ссылка, а не число).
    """
    has_citations = len(citations) > 0
    without_evidence: list[str] = []
    for sentence in _sentences(answer):
        has_marker = bool(_MARKER_RE.search(sentence))
        cleaned = _MARKER_RE.sub(" ", sentence)  # drop markers so [1] isn't a claim
        numbers = _NUMBER_RE.findall(cleaned)
        if not numbers:
            continue
        if not (has_citations and has_marker):
            without_evidence.extend(numbers)
    issues: list[str] = []
    if without_evidence and not has_citations:
        issues.append("ответ без цитат / answer has no citations")
    for num in without_evidence:
        ru = f"числовое утверждение «{num}» без ссылки"
        issues.append(f"{ru} / numeric claim «{num}» without citation")
    return AnswerValidation(
        ok=not without_evidence,
        numeric_claims_without_evidence=without_evidence,
        has_citations=has_citations,
        issues=issues,
    )
