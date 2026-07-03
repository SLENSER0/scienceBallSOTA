"""Text2Cypher retry/verifier decision logic (§12.10).

Text2Cypher (NL → Cypher) не всегда возвращает исполнимый или полезный запрос.
The §12.10 guardrail loop is: run the generated Cypher, and on failure decide
whether to *retry* the LLM (bounded by ``max_attempts``), *fall back* to a §12.2
hand-written template, or *give up* with an explicit no-answer. This module is
the pure decision core of that loop.

Two pure functions drive it:

* :func:`classify_error` maps a raw error/verifier string to one of five kinds
  via keyword rules — ``'syntax'``, ``'empty_result'``, ``'timeout'``,
  ``'guardrail'``, ``'unknown'``.
* :func:`decide` turns ``(attempt, max_attempts, error_kind)`` plus template
  availability into a frozen :class:`RetryDecision`.

Guardrail errors (disallowed / write / not-in-allowlist) are never retried — the
LLM cannot fix a policy violation by rewording, so we go straight to a template
or give up. Transient/query-shape errors (syntax, timeout, empty result) retry
while ``attempt < max_attempts``, then fall back to a template if one is
available, else give up. Nothing here touches the graph or the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Error kinds (§12.10) -------------------------------------------------
KIND_SYNTAX = "syntax"
KIND_EMPTY = "empty_result"
KIND_TIMEOUT = "timeout"
KIND_GUARDRAIL = "guardrail"
KIND_UNKNOWN = "unknown"

# --- Actions --------------------------------------------------------------
ACTION_RETRY = "retry"
ACTION_FALLBACK = "fallback_template"
ACTION_GIVE_UP = "give_up"

# Keyword rules, checked in priority order (guardrail first: a policy violation
# outranks any incidental syntax/empty wording in the same message). Each entry
# is (kind, tuple-of-lowercase-substrings).
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (KIND_GUARDRAIL, ("disallowed", "not in allowlist", "not allowlisted", "write")),
    (KIND_TIMEOUT, ("timeout", "timed out")),
    (KIND_SYNTAX, ("syntaxerror", "syntax error", "invalid input", "parse error")),
    (KIND_EMPTY, ("0 rows", "no rows", "empty result", "empty")),
)

# Decision reasons — stable, human-readable RU/EN tags for tracing.
_REASON_GUARDRAIL_FALLBACK = "guardrail нарушение: template fallback без retry"
_REASON_GUARDRAIL_GIVEUP = "guardrail нарушение: нет template, no-answer"
_REASON_RETRY = "исправимая ошибка: повторить LLM (retry)"
_REASON_EXHAUSTED_FALLBACK = "попытки исчерпаны: fallback на §12.2 template"
_REASON_EXHAUSTED_GIVEUP = "попытки исчерпаны: нет template, no-answer"


@dataclass(frozen=True)
class RetryDecision:
    """Outcome of one §12.10 retry/verifier decision.

    ``action`` is one of ``'retry'`` | ``'fallback_template'`` | ``'give_up'``.
    ``attempt`` is the 1-based attempt index the decision was made for, and
    ``reason`` is a short RU/EN trace tag naming why that action was chosen.
    """

    action: str
    attempt: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{action, attempt, reason}``."""
        return {"action": self.action, "attempt": self.attempt, "reason": self.reason}


def classify_error(error: str) -> str:
    """Classify a raw error/verifier string into a §12.10 error kind.

    Returns one of ``'syntax'`` | ``'empty_result'`` | ``'timeout'`` |
    ``'guardrail'`` | ``'unknown'``. Matching is case-insensitive substring
    matching over :data:`_RULES`, checked in priority order so that a guardrail
    signal (disallowed / write / not-in-allowlist) wins over incidental
    syntax/empty wording. An empty or unrecognized string yields ``'unknown'``.
    """
    text = (error or "").lower()
    for kind, needles in _RULES:
        if any(needle in text for needle in needles):
            return kind
    return KIND_UNKNOWN


def decide(
    attempt: int,
    max_attempts: int,
    error_kind: str,
    *,
    template_available: bool,
) -> RetryDecision:
    """Decide retry / template-fallback / give-up for one failed attempt (§12.10).

    ``attempt`` is the 1-based index of the attempt that just failed and
    ``max_attempts`` is the retry budget. ``error_kind`` is a value from
    :func:`classify_error`.

    Rules:

    * ``'guardrail'`` — never retried regardless of ``attempt``: fall back to a
      template if ``template_available`` else give up.
    * any other kind (``'syntax'`` | ``'timeout'`` | ``'empty_result'`` |
      ``'unknown'``) — retry while ``attempt < max_attempts``; at or beyond
      ``max_attempts`` fall back to a template if available, else give up.
    """
    if error_kind == KIND_GUARDRAIL:
        if template_available:
            return RetryDecision(ACTION_FALLBACK, attempt, _REASON_GUARDRAIL_FALLBACK)
        return RetryDecision(ACTION_GIVE_UP, attempt, _REASON_GUARDRAIL_GIVEUP)

    if attempt < max_attempts:
        return RetryDecision(ACTION_RETRY, attempt, _REASON_RETRY)

    if template_available:
        return RetryDecision(ACTION_FALLBACK, attempt, _REASON_EXHAUSTED_FALLBACK)
    return RetryDecision(ACTION_GIVE_UP, attempt, _REASON_EXHAUSTED_GIVEUP)
