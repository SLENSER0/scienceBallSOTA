"""Unified dead-letter / quarantine record — единый формат «карантина» (§20.11).

When a connector cannot ingest a record, or the pipeline's schema validation
rejects one, the offending payload is not silently dropped — it is parked in a
*dead-letter* (quarantine) so it can be inspected, retried, or reported. §20.11
mentions this cross-cutting format but ships no module; this is that module.

A :class:`QuarantineRecord` is a small, JSON-friendly, *content-addressed*
envelope: its ``record_id`` and ``payload_hash`` are derived deterministically
from ``(source, stage, payload)`` so the same bad payload from the same place
always yields the same identity — enabling de-duplication across restarts
without a database round-trip.

Design (§20.11):

* the raw payload is never stored — only a short ``payload_hash`` (sha256 of
  canonical ``json.dumps(payload, sort_keys=True)``, first 16 hex chars), so
  quarantine rows stay small and carry no sensitive bulk data;
* ``record_id`` = ``"quar:" + sha1(f"{source}|{stage}|{payload_hash}")[:16]``,
  a stable dedupe key;
* everything is pure and deterministic — no clock, no filesystem; the caller
  supplies ``created_at`` explicitly (defaults to empty string).

Public API:

* :class:`QuarantineRecord` — frozen 8-field record with :meth:`~QuarantineRecord.as_dict`.
* :func:`make_quarantine` — build a record from a payload mapping.
* :func:`mark_retry` — return a copy with ``retry_count`` incremented.
* :func:`is_duplicate` — same ``(source, stage, payload_hash)`` predicate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

__all__ = [
    "QuarantineRecord",
    "is_duplicate",
    "make_quarantine",
    "mark_retry",
]


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """Immutable dead-letter envelope — запись «карантина» (§20.11).

    Fields:

    * ``record_id``    — stable content-addressed id (``quar:<16 hex>``);
    * ``source``       — origin connector/system (e.g. ``"elabftw"``);
    * ``stage``        — failing stage (e.g. ``"schema_validation"``);
    * ``error_type``   — short error class name (e.g. ``"ValidationError"``);
    * ``message``      — human-readable failure detail;
    * ``payload_hash`` — sha256[:16] of the canonical payload (no raw payload);
    * ``retry_count``  — number of retry attempts so far (starts at ``0``);
    * ``created_at``   — caller-supplied timestamp string (may be empty).
    """

    record_id: str
    source: str
    stage: str
    error_type: str
    message: str
    payload_hash: str
    retry_count: int
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view — словарь из 8 полей (§20.11)."""
        return {
            "record_id": self.record_id,
            "source": self.source,
            "stage": self.stage,
            "error_type": self.error_type,
            "message": self.message,
            "payload_hash": self.payload_hash,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
        }


def _payload_hash(payload: Mapping[str, Any]) -> str:
    """sha256 of canonical JSON, first 16 hex chars — хеш полезной нагрузки (§20.11)."""
    canonical = json.dumps(dict(payload), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def make_quarantine(
    source: str,
    stage: str,
    error_type: str,
    message: str,
    payload: Mapping[str, Any],
    *,
    created_at: str = "",
) -> QuarantineRecord:
    """Build a :class:`QuarantineRecord` from a bad ``payload`` — создать запись (§20.11).

    ``payload_hash`` is the deterministic sha256[:16] of the canonical payload;
    ``record_id`` is ``"quar:" + sha1(f"{source}|{stage}|{payload_hash}")[:16]``.
    Both are pure functions of the inputs, so identical inputs always yield an
    identical identity. ``retry_count`` starts at ``0``.
    """
    payload_hash = _payload_hash(payload)
    key = f"{source}|{stage}|{payload_hash}"
    record_id = "quar:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return QuarantineRecord(
        record_id=record_id,
        source=source,
        stage=stage,
        error_type=error_type,
        message=message,
        payload_hash=payload_hash,
        retry_count=0,
        created_at=created_at,
    )


def mark_retry(rec: QuarantineRecord) -> QuarantineRecord:
    """Return a copy with ``retry_count`` incremented by one — отметить повтор (§20.11)."""
    return replace(rec, retry_count=rec.retry_count + 1)


def is_duplicate(a: QuarantineRecord, b: QuarantineRecord) -> bool:
    """Whether ``a`` and ``b`` describe the same bad payload — дубликат ли (§20.11).

    Two records are duplicates when they share ``source``, ``stage`` and
    ``payload_hash`` — i.e. the same payload failed at the same place in the
    same source (regardless of retry count or timestamp).
    """
    return a.source == b.source and a.stage == b.stage and a.payload_hash == b.payload_hash
