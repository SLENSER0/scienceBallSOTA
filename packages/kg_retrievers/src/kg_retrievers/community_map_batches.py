"""Multi-batch map-context planning under a per-context token limit (§11.7).

Планирование пакетов (batches) для map-фазы community-summarisation: сортирует
отчёты по (score убыв., community_id возр.), затем жадно (greedy) наполняет
пакет, добавляя ``est_tokens`` очередного отчёта, пока сумма пакета остаётся
``<= max_context_tokens``; при переполнении открывается новый пакет. Отчёт, чей
``est_tokens`` сам по себе превышает лимит, отбрасывается (dropped). Пакеты сверх
``max_batches`` также отбрасываются.

English: :func:`plan_batches` takes community reports (each a mapping with a
``community_id``, a ranking ``score`` and an ``est_tokens`` estimate), orders
them by descending score with ``community_id`` ascending breaking ties, then
greedily packs them into :class:`MapBatch` groups whose per-batch token total
never exceeds ``max_context_tokens``. A report whose own ``est_tokens`` already
exceeds the limit can never fit and is dropped; if ``max_batches`` is set, any
batch past that count is dropped along with its ids. The result is a frozen
:class:`BatchPlan`. Pure in-memory transform: reads no store, writes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MapBatch:
    """One planned map-context batch (§11.7).

    - ``index`` — zero-based position of the batch in the plan;
    - ``community_ids`` — ids packed into this batch, in packing order;
    - ``tokens`` — summed ``est_tokens`` of the batch, ``<= max_context_tokens``.
    """

    index: int
    community_ids: tuple[str, ...]
    tokens: int

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{index, community_ids, tokens}`` (ids as a list)."""
        return {
            "index": self.index,
            "community_ids": list(self.community_ids),
            "tokens": self.tokens,
        }


@dataclass(frozen=True)
class BatchPlan:
    """A full multi-batch plan (§11.7).

    - ``batches`` — the packed :class:`MapBatch` groups, ordered by ``index``;
    - ``n_batches`` — ``len(batches)`` (convenience mirror);
    - ``dropped`` — community ids that never landed in a batch (too large for the
      limit, or beyond ``max_batches``), in the order they were considered.
    """

    batches: tuple[MapBatch, ...]
    n_batches: int
    dropped: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{batches, n_batches, dropped}`` (nested batches expanded)."""
        return {
            "batches": [batch.as_dict() for batch in self.batches],
            "n_batches": self.n_batches,
            "dropped": list(self.dropped),
        }


def _coerce_int(value: object, default: int = 0) -> int:
    """Coerce a raw cell to ``int`` (``bool`` and non-numerics fall back to ``default``)."""
    if isinstance(value, bool):  # bool is an int subclass — never a token count
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    """Coerce a raw cell to ``float`` (``bool`` and non-numerics fall back to ``default``)."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def plan_batches(
    reports: Sequence[Mapping],
    *,
    max_context_tokens: int,
    max_batches: int | None = None,
) -> BatchPlan:
    """Greedily pack community reports into token-bounded map batches (§11.7).

    Reports are sorted by descending ``score`` with ``community_id`` ascending breaking
    ties, then packed in order: a report's ``est_tokens`` is added to the current batch
    while the running total stays ``<= max_context_tokens``; on overflow a new batch is
    started. A single report whose ``est_tokens`` already exceeds ``max_context_tokens``
    can never fit and is added to ``dropped``. When ``max_batches`` is given, batches
    beyond that count are dropped and their ids collected into ``dropped``. Empty
    ``reports`` yields ``n_batches == 0``. Every ``community_id`` ends up in exactly one
    batch or in ``dropped``.
    """
    if not reports:
        return BatchPlan(batches=(), n_batches=0, dropped=())

    ordered = sorted(
        reports,
        key=lambda r: (-_coerce_float(r.get("score")), str(r.get("community_id"))),
    )

    packed: list[list[str]] = []
    packed_tokens: list[int] = []
    dropped: list[str] = []
    current_ids: list[str] = []
    current_tokens = 0

    for report in ordered:
        community_id = str(report.get("community_id"))
        est_tokens = _coerce_int(report.get("est_tokens"))
        if est_tokens > max_context_tokens:
            dropped.append(community_id)  # too large for any batch
            continue
        if current_ids and current_tokens + est_tokens > max_context_tokens:
            packed.append(current_ids)  # overflow — seal the current batch
            packed_tokens.append(current_tokens)
            current_ids = []
            current_tokens = 0
        current_ids.append(community_id)
        current_tokens += est_tokens
    if current_ids:
        packed.append(current_ids)
        packed_tokens.append(current_tokens)

    if max_batches is not None and len(packed) > max_batches:
        keep = max(max_batches, 0)
        for extra_ids in packed[keep:]:
            dropped.extend(extra_ids)  # batches past the cap are dropped
        packed = packed[:keep]
        packed_tokens = packed_tokens[:keep]

    batches = tuple(
        MapBatch(index=i, community_ids=tuple(ids), tokens=packed_tokens[i])
        for i, ids in enumerate(packed)
    )
    return BatchPlan(batches=batches, n_batches=len(batches), dropped=tuple(dropped))
