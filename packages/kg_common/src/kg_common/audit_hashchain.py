"""Tamper-evident append-only audit hash-chain — цепочка хешей аудита (§10.8).

Privileged actions must leave a trail that cannot be silently rewritten. This
module implements a *cryptographic hash-chain* («prev_hash → hash»): every audit
record embeds the hash of its predecessor, so altering any earlier record breaks
every hash that follows it and :func:`verify_chain` pinpoints the first tampered
link.

Each :class:`AuditRecord` carries a ``hash`` computed by :func:`compute_hash`
over a *canonical* JSON encoding of its ordered fields (``prev_hash`` included),
making the digest deterministic and independent of dict insertion order. The
first record links to :data:`GENESIS_HASH`, a fixed all-zero sentinel.

Everything here is deterministic and side-effect free: no wall-clock, no I/O and
no mutation of the input chain — :func:`append` returns a fresh record for the
caller to store.

Public API:

* :data:`GENESIS_HASH`   — fixed sentinel ``prev_hash`` for the first record.
* :class:`AuditRecord`   — frozen chain link with :meth:`AuditRecord.as_dict`.
* :func:`compute_hash`   — sha256 hex over the ordered, canonical fields.
* :func:`append`         — build and link the next record onto a chain.
* :func:`verify_chain`   — check integrity, reporting the first bad ``seq``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

__all__ = [
    "GENESIS_HASH",
    "AuditRecord",
    "append",
    "compute_hash",
    "verify_chain",
]

# Fixed sentinel the first record links back to — «генезис-хеш» (§10.8).
# 64 zero hex digits mirror the width of a sha256 digest without being one.
GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditRecord:
    """A single immutable link in the audit hash-chain — запись цепочки (§10.8).

    ``seq`` is the zero-based position, ``actor_id`` the principal, ``action`` the
    verb, ``target_type`` / ``target_id`` the object acted upon and ``payload`` any
    extra context. ``prev_hash`` is the ``hash`` of the preceding record (or
    :data:`GENESIS_HASH` for the first), and ``hash`` is this record's digest as
    produced by :func:`compute_hash`.

    The dataclass is frozen so a record, once linked, cannot be mutated in place —
    tampering requires rebuilding it, which is exactly what :func:`verify_chain`
    detects.
    """

    seq: int
    actor_id: str
    action: str
    target_type: str
    target_id: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view of the record — сериализация записи (§10.8).

        Returns every field, including ``prev_hash`` and ``hash``, so the record
        can be persisted or transmitted and later re-verified. ``payload`` is
        copied so callers cannot mutate the frozen record's dict through the view.
        """
        return {
            "seq": self.seq,
            "actor_id": self.actor_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "payload": dict(self.payload),
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


def compute_hash(
    prev_hash: str,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any],
) -> str:
    """sha256 hex over the ordered, canonical fields — вычислить хеш (§10.8).

    The fields are packed into an ordered mapping and serialized with
    :func:`json.dumps` using ``sort_keys=True`` and compact separators, so the
    digest is *canonical*: it depends only on the values, never on dict insertion
    order or incidental whitespace. Including *prev_hash* is what chains a record
    to its predecessor. The result is a 64-character lowercase hex string.
    """
    material = {
        "prev_hash": prev_hash,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "payload": payload,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def append(
    chain: list[AuditRecord],
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any],
) -> AuditRecord:
    """Build and link the next record onto *chain* — добавить запись (§10.8).

    The new record's ``seq`` is ``len(chain)`` and its ``prev_hash`` is the
    ``hash`` of the last existing record, or :data:`GENESIS_HASH` when the chain is
    empty. The record's own ``hash`` is computed by :func:`compute_hash` over its
    linked fields. This function does *not* mutate *chain* — it returns the fresh
    record and leaves storage to the caller.
    """
    prev_hash = chain[-1].hash if chain else GENESIS_HASH
    record_hash = compute_hash(
        prev_hash,
        actor_id,
        action,
        target_type,
        target_id,
        payload,
    )
    return AuditRecord(
        seq=len(chain),
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        prev_hash=prev_hash,
        hash=record_hash,
    )


def verify_chain(chain: list[AuditRecord]) -> tuple[bool, int]:
    """Check chain integrity — проверить целостность цепочки (§10.8).

    Walks the chain in order and, for each record, re-derives its expected
    ``hash`` from its stored fields and confirms its ``prev_hash`` links to the
    preceding record's ``hash`` (or :data:`GENESIS_HASH` for the first). Returns
    ``(True, -1)`` when the chain is fully intact, otherwise ``(False, seq)`` where
    *seq* is the position of the first record that fails to verify.
    """
    expected_prev = GENESIS_HASH
    for record in chain:
        if record.prev_hash != expected_prev:
            return (False, record.seq)
        recomputed = compute_hash(
            record.prev_hash,
            record.actor_id,
            record.action,
            record.target_type,
            record.target_id,
            record.payload,
        )
        if recomputed != record.hash:
            return (False, record.seq)
        expected_prev = record.hash
    return (True, -1)
