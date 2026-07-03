"""§13.20 semantic-search индекс по долговременной памяти / semantic index over Store memory.

While :mod:`user_memory` covers the *structural* side of §13.20 long-term memory —
namespacing per user and recency pruning — it explicitly leaves the "индекс для
semantic search по памяти (embeddings)" unimplemented. This module fills that gap with
pure, deterministic helpers that rank stored memory records by embedding similarity to a
query vector, so the agent can recall the *most relevant* facts (not merely the newest).

Everything is store-free and network-free:

* :func:`cosine` — cosine similarity of two vectors, ``0.0`` when either has zero norm.
* :func:`search_memory` — drop expired records, score by :func:`cosine`, filter by
  ``min_score``, sort by score desc then key asc, and truncate to ``top_k``.

Each input record is a plain dict ``{'key', 'value', 'embedding', 'expires_at'}`` where
``expires_at`` is an absolute timestamp (or ``None`` for never-expiring). Results are
frozen :class:`MemoryMatch` objects, JSON-serialisable via :meth:`MemoryMatch.as_dict`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryMatch:
    """One ranked memory hit (§13.20): a record key with its similarity ``score``.

    Frozen and JSON-serialisable via :meth:`as_dict`. ``score`` is the cosine similarity
    of the record embedding to the query vector (сходство / similarity), ``value`` is the
    stored payload carried through unchanged.
    """

    key: str
    score: float
    value: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{key, score, value}`` (stable order / стабильный порядок)."""
        return {
            "key": self.key,
            "score": self.score,
            "value": dict(self.value),
        }


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors (косинусное сходство / cosine similarity).

    Returns ``dot(a, b) / (‖a‖·‖b‖)``. If either vector has zero norm (нулевая норма /
    zero magnitude), similarity is undefined, so ``0.0`` is returned instead of dividing
    by zero. E.g. ``cosine([1, 0], [1, 0]) == 1.0``; ``cosine([1, 0], [0, 1]) == 0.0``.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_memory(
    records: list[dict[str, Any]],
    query_vec: Sequence[float],
    top_k: int,
    now: float,
    min_score: float = 0.0,
) -> list[MemoryMatch]:
    """Rank long-term memory records by embedding similarity to ``query_vec`` (§13.20).

    Each ``record`` is ``{'key', 'value', 'embedding', 'expires_at'}``. Records whose
    ``expires_at`` is not ``None`` and ``<= now`` are dropped as expired (истёкшие /
    lapsed); ``expires_at is None`` never expires. Survivors are scored with
    :func:`cosine` against ``query_vec``, filtered to ``score >= min_score``, sorted by
    score descending then ``key`` ascending (детерминированный порядок / deterministic
    tie-break), and truncated to ``top_k``. ``top_k <= 0`` → ``[]``.
    """
    if top_k <= 0:
        return []
    matches: list[MemoryMatch] = []
    for record in records:
        expires_at = record.get("expires_at")
        if expires_at is not None and expires_at <= now:
            continue
        score = cosine(record["embedding"], query_vec)
        if score < min_score:
            continue
        matches.append(MemoryMatch(key=record["key"], score=score, value=record["value"]))
    matches.sort(key=lambda m: (-m.score, m.key))
    return matches[:top_k]
