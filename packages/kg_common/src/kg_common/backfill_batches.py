"""Backfill run batching — нарезка добора на прогоны (§9.3).

A *partition backfill* — e.g. «reprocess every doc of a source after a schema
change» — must be split into bounded per-run batches so no single scheduler run
tries to re-materialise the whole partition set at once. This module owns that
split, and *only* that split: it is distinct from :mod:`kg_common.backfill_plan`,
which decides *which* partitions need a backfill in the first place. Here every
input key is taken as already-chosen; we merely chunk it, order-preserving, into
fixed-size runs.

* :class:`BackfillBatch` — one frozen, ordered run of partition keys.
* :func:`chunk_partitions` — split an ordered key sequence into batches.
* :func:`backfill_summary` — headline counts over a batch sequence.

Everything is a pure function of its inputs and side-effect free.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "BackfillBatch",
    "chunk_partitions",
    "backfill_summary",
]


@dataclass(frozen=True, slots=True)
class BackfillBatch:
    """One backfill run — один прогон добора (§9.3).

    ``index`` is the 0-based position of this batch in the split; ``partition_keys``
    is the ordered slice of keys handled by the run. The final batch of a split may
    hold fewer keys than the requested ``batch_size`` — последний прогон короче.
    """

    index: int
    partition_keys: tuple[str, ...]

    @property
    def size(self) -> int:
        """Number of partition keys in this batch — размер прогона (§9.3)."""
        return len(self.partition_keys)

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — прогон как словарь (§9.3)."""
        return {
            "index": self.index,
            "partition_keys": list(self.partition_keys),
            "size": self.size,
        }


def chunk_partitions(keys: Sequence[str], batch_size: int) -> tuple[BackfillBatch, ...]:
    """Split ``keys`` into ``batch_size``-bounded batches — нарезка (§9.3).

    Order is preserved: concatenating the batches' ``partition_keys`` reconstructs
    ``keys`` exactly. The last batch may be smaller than ``batch_size``. An empty
    input yields an empty tuple. ``batch_size < 1`` raises :class:`ValueError`.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    batches: list[BackfillBatch] = []
    for index, start in enumerate(range(0, len(keys), batch_size)):
        chunk = tuple(keys[start : start + batch_size])
        batches.append(BackfillBatch(index=index, partition_keys=chunk))
    return tuple(batches)


def backfill_summary(batches: Sequence[BackfillBatch]) -> dict:
    """Headline counts over ``batches`` — сводка по прогонам (§9.3).

    Returns ``{'batches', 'total_partitions', 'max_batch_size'}`` where
    ``total_partitions`` is the sum of batch sizes and ``max_batch_size`` is the
    largest batch size (``0`` for an empty input).
    """
    sizes = [batch.size for batch in batches]
    return {
        "batches": len(batches),
        "total_partitions": sum(sizes),
        "max_batch_size": max(sizes) if sizes else 0,
    }
