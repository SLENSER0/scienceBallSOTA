"""Entity/edge -> NDJSON stream — потоковая сериализация в NDJSON (§22).

Newline-delimited JSON (NDJSON) is the interchange format for bulk export /
ETL and for building LLM fine-tune corpora: one self-describing JSON object per
line, so a stream can be produced and consumed record-by-record without ever
holding the whole graph in memory. The repo already *parses* JSON in a few
places, but nothing *emits* NDJSON — this module fills that gap for node and
edge records.

Each line is a single :func:`json.dumps` object with a reserved ``"kind"``
discriminator (``"node"`` or ``"edge"``) merged with the record payload. Keys
are emitted sorted (``sort_keys=True``) for deterministic, hand-checkable and
diff-friendly output, and ``ensure_ascii=False`` keeps Cyrillic (and any other
non-ASCII) text readable and byte-round-trippable — кириллица сохраняется.

The ``"kind"`` discriminator always wins: a payload that happens to carry its
own ``"kind"`` key cannot overwrite the record's real kind — приоритет за
дискриминатором. Round-trip is total: :func:`iter_ndjson` skips blank lines and
reconstructs the emitted objects, so ``iter_ndjson(to_ndjson(records))`` yields
the same dicts (payload plus the ``"kind"`` key).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "NdjsonRecord",
    "entity_record",
    "edge_record",
    "to_ndjson",
    "iter_ndjson",
]

#: Reserved discriminator key; the record's ``kind`` always wins over payload.
_KIND_KEY = "kind"


@dataclass(frozen=True)
class NdjsonRecord:
    """One NDJSON record — запись потока: ``kind`` + произвольный payload (§22).

    ``kind`` is the reserved discriminator (``"node"`` / ``"edge"``); ``payload``
    is the record body. :meth:`as_dict` renders the wire object: the payload
    merged under the ``"kind"`` discriminator, with the discriminator taking
    precedence over any collision with that same key inside ``payload``.
    """

    kind: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Wire object: ``{**payload, "kind": kind}`` — дискриминатор поверх."""
        # Spread payload first, then force the reserved key: record kind wins.
        return {**self.payload, _KIND_KEY: self.kind}


def entity_record(node: dict[str, Any]) -> NdjsonRecord:
    """Wrap a node dict as a ``kind='node'`` record — узел графа (§22)."""
    return NdjsonRecord(kind="node", payload=node)


def edge_record(edge: dict[str, Any]) -> NdjsonRecord:
    """Wrap an edge dict as a ``kind='edge'`` record — ребро графа (§22)."""
    return NdjsonRecord(kind="edge", payload=edge)


def to_ndjson(records: Iterable[NdjsonRecord]) -> str:
    """Serialise ``records`` to an NDJSON string — сериализация потока (§22).

    Every record becomes exactly one line: a ``json.dumps`` object with
    ``sort_keys=True`` (deterministic key order — ``"id"`` before ``"name"``)
    and ``ensure_ascii=False`` (Cyrillic survives). Each line is terminated by a
    single ``"\\n"``, so N records yield N newline-terminated lines. An empty
    iterable yields ``""`` (no trailing newline).
    """
    parts: list[str] = []
    for record in records:
        line = json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False)
        parts.append(line + "\n")
    return "".join(parts)


def iter_ndjson(text: str) -> list[dict[str, Any]]:
    """Parse an NDJSON string back to dicts — разбор потока (§22).

    Splits on newlines and JSON-decodes each non-blank line, skipping blank
    lines (including a trailing one left by :func:`to_ndjson`). Total inverse of
    :func:`to_ndjson`: ``iter_ndjson(to_ndjson(recs))`` reproduces each record's
    :meth:`NdjsonRecord.as_dict` (payload plus the ``"kind"`` discriminator).
    """
    out: list[dict[str, Any]] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out
