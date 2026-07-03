"""§13.20 долговременная память Store — writeback / long-term Store write candidates.

Where :mod:`user_memory` models the *storage* side of §13.20 long-term memory (frozen
``MemoryRecord`` facts, namespacing, pruning), this module is the *source* side: it
**derives** what a finished session should write back into the Store. A completed
session yields three kinds of durable facts —

* confirmed canonical entities (mention → canonical id) as ``entity_alias`` writes;
* frequently used filters as ``preferred_filter`` writes;
* stated user preferences as ``preference`` writes.

The single unit is a frozen :class:`MemoryWrite` — a JSON-serialisable write candidate
carrying ``key``/``value``/``kind``/``confidence``. Pure, deterministic helpers turn a
session's end state into a list of these candidates without touching any store or
network (без стора и сети / no store, no network), so the derivation is hand-checkable
in isolation from the real ``PostgresStore``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Kinds a write candidate may carry (виды кандидатов / candidate kinds). Others raise.
KINDS: frozenset[str] = frozenset({"entity_alias", "preferred_filter", "preference"})


@dataclass(frozen=True)
class MemoryWrite:
    """One long-term Store write candidate derived from a session (§13.20).

    Frozen and JSON-serialisable via :meth:`as_dict`. ``kind`` must be one of
    :data:`KINDS` (иначе ошибка / else raises). ``confidence`` is the derivation's
    strength in ``[0, 1]`` — e.g. an entity's own confidence, or a filter's frequency.
    """

    key: str
    value: Any
    kind: str
    confidence: float

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind!r} / неизвестный вид записи")

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{key, value, kind, confidence}`` (stable order / round-trips)."""
        return {
            "key": self.key,
            "value": self.value,
            "kind": self.kind,
            "confidence": self.confidence,
        }


def from_confirmed_entities(
    entities: list[dict[str, Any]], threshold: float = 0.8
) -> list[MemoryWrite]:
    """Derive ``entity_alias`` writes from confirmed canonical entities (§13.20).

    Each entity is ``{'mention', 'canonical_id', 'confidence'}``. Only entities whose
    ``confidence >= threshold`` are kept (порог уверенности / confidence gate): each
    yields one write with ``kind='entity_alias'``, ``key=f"alias:{mention}"``, and
    ``value=canonical_id`` (напр. mention='Асп', canonical_id='CHEBI:1' → key
    ``"alias:Асп"``). Entities below the threshold are skipped.
    """
    writes: list[MemoryWrite] = []
    for entity in entities:
        confidence = float(entity["confidence"])
        if confidence < threshold:
            continue
        mention = entity["mention"]
        writes.append(
            MemoryWrite(
                key=f"alias:{mention}",
                value=entity["canonical_id"],
                kind="entity_alias",
                confidence=confidence,
            )
        )
    return writes


def from_filter_history(
    filter_history: list[dict[str, Any]], min_count: int = 2
) -> list[MemoryWrite]:
    """Derive ``preferred_filter`` writes from a session's filter history (§13.20).

    ``filter_history`` is the list of filter dicts applied during the session (repeats
    allowed). A filter seen at least ``min_count`` times becomes one write with
    ``kind='preferred_filter'`` and ``confidence=count/len(filter_history)`` (частота /
    frequency, напр. 3 of 5 → 0.6). Filters seen fewer than ``min_count`` times are
    skipped. The ``key`` is a stable serialisation of the filter and ``value`` is the
    filter dict itself; distinct filters are reported in first-seen order.
    """
    total = len(filter_history)
    if total == 0:
        return []
    order: list[str] = []
    counts: dict[str, int] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for filt in filter_history:
        fkey = _filter_key(filt)
        if fkey not in counts:
            order.append(fkey)
            counts[fkey] = 0
            payloads[fkey] = filt
        counts[fkey] += 1
    writes: list[MemoryWrite] = []
    for fkey in order:
        count = counts[fkey]
        if count < min_count:
            continue
        writes.append(
            MemoryWrite(
                key=f"filter:{fkey}",
                value=payloads[fkey],
                kind="preferred_filter",
                confidence=count / total,
            )
        )
    return writes


def collect_writes(state: dict[str, Any], threshold: float = 0.8) -> list[MemoryWrite]:
    """Collect all write candidates from a finished session ``state`` (§13.20).

    Combines :func:`from_confirmed_entities` over ``state['confirmed_entities']`` and
    :func:`from_filter_history` over ``state['filter_history']`` (missing keys default
    to empty). An empty state yields ``[]`` (пустое состояние → пусто / empty in, empty
    out). Entity-alias writes precede preferred-filter writes.
    """
    entities = state.get("confirmed_entities", [])
    filters = state.get("filter_history", [])
    writes = from_confirmed_entities(entities, threshold=threshold)
    writes.extend(from_filter_history(filters))
    return writes


def _filter_key(filt: dict[str, Any]) -> str:
    """Stable string key for a filter dict (order-independent / устойчивый ключ)."""
    return ";".join(f"{k}={filt[k]!r}" for k in sorted(filt))
