"""Dead-letter records + transient/fatal error classification (§9.7).

Pipeline stages (parse / extract / load …) fail for two very different
reasons and must be handled differently («транзиентные vs фатальные ошибки»,
§9.7):

* **transient** — timeouts, dropped connections, temporary upstream 5xx. The
  same input может пройти на повторе, so these are *retried* up to a bounded
  number of attempts.
* **fatal** — schema validation, unparseable payloads, permanent rejects.
  Retrying is pointless — the document goes straight to the dead-letter queue.
* **unknown** — an ``error_type`` we have not classified yet. Treated
  conservatively as non-retryable (terminal), same as fatal.

A :class:`DeadLetterRecord` is the immutable envelope written to the DLQ; it
carries enough context (``doc_id`` / ``stage`` / ``error_type`` / ``message`` /
``attempts``) to triage or replay without re-deriving anything.

* :data:`TRANSIENT_TYPES` / :data:`FATAL_TYPES` — the classification tables.
* :func:`classify_error`  — ``'transient' | 'fatal' | 'unknown'``.
* :func:`should_retry`    — transient AND attempt budget не исчерпан.
* :func:`to_dead_letter`  — build a record, computing ``terminal``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Retryable failure types — «можно повторить» (§9.7).
TRANSIENT_TYPES: frozenset[str] = frozenset(
    {
        "timeout",
        "connection_reset",
        "connection_error",
        "temporary_unavailable",
        "rate_limited",
        "upstream_5xx",
    }
)

# Permanent failure types — retry бесполезен, сразу в DLQ (§9.7).
FATAL_TYPES: frozenset[str] = frozenset(
    {
        "schema_validation",
        "parse_error",
        "unsupported_format",
        "permanent_reject",
        "corrupt_payload",
    }
)

# Classification labels — стабильные строки для веток логики (§9.7).
TRANSIENT = "transient"
FATAL = "fatal"
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DeadLetterRecord:
    """Immutable dead-letter envelope for a failed document (§9.7).

    ``terminal`` marks whether the pipeline has given up on this document
    (``True`` = no further retries — фатально/исчерпаны попытки).
    """

    doc_id: str
    stage: str
    error_type: str
    message: str
    attempts: int
    terminal: bool

    def as_dict(self) -> dict[str, object]:
        """Structured, JSON-friendly view — запись для очереди DLQ (§9.7)."""
        return {
            "doc_id": self.doc_id,
            "stage": self.stage,
            "error_type": self.error_type,
            "message": self.message,
            "attempts": self.attempts,
            "terminal": self.terminal,
        }


def classify_error(error_type: str) -> str:
    """Classify ``error_type`` as transient / fatal / unknown (§9.7).

    Unknown types are *not* assumed transient — an unclassified error is
    treated conservatively (non-retryable) by the callers below.
    """
    if error_type in TRANSIENT_TYPES:
        return TRANSIENT
    if error_type in FATAL_TYPES:
        return FATAL
    return UNKNOWN


def should_retry(error_type: str, attempt: int, max_attempts: int) -> bool:
    """Whether to retry: transient AND attempt budget не исчерпан (§9.7).

    ``attempt`` is the 1-based number of the attempt that just failed; a retry
    is permitted only while ``attempt < max_attempts`` and only for transient
    errors. Fatal / unknown errors never retry.
    """
    return classify_error(error_type) == TRANSIENT and attempt < max_attempts


def to_dead_letter(
    doc_id: str,
    stage: str,
    error_type: str,
    message: str,
    attempts: int,
    max_attempts: int = 3,
) -> DeadLetterRecord:
    """Build a :class:`DeadLetterRecord`, computing ``terminal`` (§9.7).

    ``terminal`` is ``True`` when the error is not transient (fatal / unknown
    are always terminal) **or** the transient retry budget is exhausted
    (``attempts >= max_attempts``).
    """
    is_transient = classify_error(error_type) == TRANSIENT
    terminal = (not is_transient) or attempts >= max_attempts
    return DeadLetterRecord(
        doc_id=doc_id,
        stage=stage,
        error_type=error_type,
        message=message,
        attempts=attempts,
        terminal=terminal,
    )
