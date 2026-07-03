"""Per-connector sync metrics for observability — метрики синхронизации (§20.13).

Every connector run emits a handful of counters — how many records were synced,
how many were skipped, how many entity merges resolved automatically versus were
routed to human review, and how many errors were hit. This module gives those
counters a single frozen shape and a couple of pure folds so a dashboard can
aggregate across many runs without depending on any connector internals.

Everything here is deterministic and side-effect free:

* :class:`ConnectorMetrics` — frozen counter record with :meth:`ConnectorMetrics.as_dict`.
* :func:`combine`    — sum two records field-by-field («сложить две метрики»).
* :func:`aggregate`  — fold :func:`combine` over a list (empty → all zeros).
* :func:`success_rate` — ``records_synced / (records_synced + errors)``, ``0.0`` on
  an empty denominator («доля успеха», защита от деления на ноль).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

__all__ = [
    "ConnectorMetrics",
    "aggregate",
    "combine",
    "success_rate",
]


@dataclass(frozen=True, slots=True)
class ConnectorMetrics:
    """Immutable per-connector counters — счётчики одного коннектора (§20.13).

    ``records_synced``/``records_skipped`` count rows written versus skipped;
    ``merge_auto``/``merge_review`` count entity merges resolved automatically
    versus routed to review; ``errors`` counts failures. All fields default to
    ``0`` so a fresh run starts from an all-zero record. The value is a plain
    frozen record so it can be hashed, compared and serialized.
    """

    records_synced: int = 0
    records_skipped: int = 0
    merge_auto: int = 0
    merge_review: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        """JSON-friendly view — пять счётчиков как словарь (§20.13)."""
        return {
            "records_synced": self.records_synced,
            "records_skipped": self.records_skipped,
            "merge_auto": self.merge_auto,
            "merge_review": self.merge_review,
            "errors": self.errors,
        }


def combine(a: ConnectorMetrics, b: ConnectorMetrics) -> ConnectorMetrics:
    """Sum two metric records field-by-field — сложить две метрики (§20.13).

    Returns a new :class:`ConnectorMetrics` whose every counter is the sum of the
    corresponding counters in ``a`` and ``b``; neither input is mutated.
    """
    return ConnectorMetrics(
        records_synced=a.records_synced + b.records_synced,
        records_skipped=a.records_skipped + b.records_skipped,
        merge_auto=a.merge_auto + b.merge_auto,
        merge_review=a.merge_review + b.merge_review,
        errors=a.errors + b.errors,
    )


def aggregate(metrics: list[ConnectorMetrics]) -> ConnectorMetrics:
    """Fold :func:`combine` over ``metrics`` — свести список метрик (§20.13).

    An empty list yields an all-zero :class:`ConnectorMetrics` (the identity of
    :func:`combine`), so callers never have to special-case «нет прогонов».
    """
    result = ConnectorMetrics()
    for item in metrics:
        result = combine(result, item)
    return result


def success_rate(m: ConnectorMetrics) -> float:
    """Share of synced records over synced-plus-errors — доля успеха (§20.13).

    Returns ``records_synced / (records_synced + errors)``. When that denominator
    is ``0`` (no records and no errors) the rate is ``0.0`` rather than a
    ``ZeroDivisionError`` — «защита от деления на ноль».
    """
    denominator = m.records_synced + m.errors
    if denominator == 0:
        return 0.0
    return m.records_synced / denominator


# Sanity check: the record has exactly the five documented counter fields.
assert tuple(f.name for f in fields(ConnectorMetrics)) == (
    "records_synced",
    "records_skipped",
    "merge_auto",
    "merge_review",
    "errors",
)
