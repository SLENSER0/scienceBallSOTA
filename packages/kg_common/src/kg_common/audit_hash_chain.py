"""Tamper-evident hash-chain for the audit log — цепочка хэшей аудита (§10.8).

The append-only ``audit_log`` must be *tamper-evident*: any after-the-fact edit,
insertion or reordering of records has to be detectable. This module implements
the ``prev_hash -> hash`` chaining described in §10.8, keeping it strictly
separate from :mod:`kg_common.audit_formatter`, which only *formats* records and
performs no chaining («audit_formatter форматирует, но не связывает записи»).

Each record commits to the whole history before it:

* ``payload_hash`` = SHA-256 of the canonical JSON of the record payload
  (``json.dumps(..., sort_keys=True)``), so key order never changes the hash.
* ``prev_hash``    = the ``hash`` of the preceding record, or :data:`GENESIS_PREV`
  (64 zero hex chars) for the very first record.
* ``hash``         = SHA-256 of ``prev_hash + payload_hash``.

Because every ``hash`` folds in the previous one, editing an early record breaks
the link to every record that follows it — that is what makes the log
tamper-evident («любое изменение ломает цепочку»).

Everything here is deterministic and side-effect free — no wall-clock, no I/O.

Public API:

* :class:`ChainedRecord`  — frozen ``{index, payload_hash, prev_hash, hash}``
  record with :meth:`ChainedRecord.as_dict`.
* :data:`GENESIS_PREV`    — the ``prev_hash`` sentinel of the first record.
* :func:`hash_payload`    — canonical SHA-256 hex of a payload mapping.
* :func:`append_record`   — derive the next record from a chain + payload.
* :func:`build_chain`     — build a full chain from a sequence of payloads.
* :func:`verify_chain`    — check that a chain is internally consistent.
* :func:`find_break`      — index of the first inconsistent record, or ``None``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "GENESIS_PREV",
    "ChainedRecord",
    "append_record",
    "build_chain",
    "find_break",
    "hash_payload",
    "verify_chain",
]

#: ``prev_hash`` sentinel for the first record — 64 zero hex chars (§10.8).
GENESIS_PREV = "0" * 64


@dataclass(frozen=True)
class ChainedRecord:
    """A single link in the audit hash-chain — звено цепочки (§10.8).

    ``index`` is the 0-based position of the record in the chain, ``payload_hash``
    the canonical hash of its payload, ``prev_hash`` the ``hash`` of the preceding
    record (or :data:`GENESIS_PREV` for the first) and ``hash`` the commitment
    ``SHA-256(prev_hash + payload_hash)``. The dataclass is frozen so a record can
    be shared and serialized without risk of accidental mutation.
    """

    index: int
    payload_hash: str
    prev_hash: str
    hash: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view — ``{index, payload_hash, prev_hash, hash}`` (§10.8)."""
        return {
            "index": self.index,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


def _sha256_hex(data: str) -> str:
    """SHA-256 hex digest of a UTF-8 string — хэш SHA-256 (§10.8)."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def hash_payload(payload: Mapping[str, Any]) -> str:
    """Canonical SHA-256 hex of a payload — хэш полезной нагрузки (§10.8).

    The payload is serialized with ``json.dumps(..., sort_keys=True)`` so that key
    order is irrelevant — ``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}`` hash to the
    same value. Separators are fixed to keep the encoding stable across platforms.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(canonical)


def _link_hash(prev_hash: str, payload_hash: str) -> str:
    """Commitment ``SHA-256(prev_hash + payload_hash)`` — хэш звена (§10.8)."""
    return _sha256_hex(prev_hash + payload_hash)


def append_record(
    chain: Sequence[ChainedRecord],
    payload: Mapping[str, Any],
) -> ChainedRecord:
    """Derive the next record for *chain* from *payload* — добавить звено (§10.8).

    ``prev_hash`` is the ``hash`` of the last record in *chain*, or
    :data:`GENESIS_PREV` when *chain* is empty; ``index`` continues the sequence.
    The function is pure — *chain* is not mutated; the caller appends the returned
    record itself.
    """
    prev_hash = chain[-1].hash if chain else GENESIS_PREV
    payload_hash = hash_payload(payload)
    return ChainedRecord(
        index=len(chain),
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        hash=_link_hash(prev_hash, payload_hash),
    )


def build_chain(payloads: Sequence[Mapping[str, Any]]) -> list[ChainedRecord]:
    """Build a full hash-chain from *payloads* — построить цепочку (§10.8).

    Records are produced in order, each linked to the previous one; the first
    record's ``prev_hash`` is :data:`GENESIS_PREV`. An empty *payloads* yields an
    empty chain.
    """
    chain: list[ChainedRecord] = []
    for payload in payloads:
        chain.append(append_record(chain, payload))
    return chain


def find_break(chain: Sequence[ChainedRecord]) -> int | None:
    """Index of the first inconsistent record — первый разрыв цепочки (§10.8).

    Walks the chain and recomputes each link: a record is broken when its
    ``prev_hash`` does not match the previous record's ``hash`` (or
    :data:`GENESIS_PREV` for the first record), or when its stored ``hash`` does
    not equal ``SHA-256(prev_hash + payload_hash)``. Returns the 0-based index of
    the first such record, or ``None`` when the whole chain is consistent.
    """
    expected_prev = GENESIS_PREV
    for index, record in enumerate(chain):
        if record.prev_hash != expected_prev:
            return index
        if record.hash != _link_hash(record.prev_hash, record.payload_hash):
            return index
        expected_prev = record.hash
    return None


def verify_chain(chain: Sequence[ChainedRecord]) -> bool:
    """True when *chain* is internally consistent — проверить цепочку (§10.8).

    A thin boolean wrapper over :func:`find_break`: the chain is valid exactly when
    no break is found. An empty chain is trivially valid.
    """
    return find_break(chain) is None
