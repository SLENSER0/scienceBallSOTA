"""Freshness / wall-clock SLA for scheduled corpus assets (§9.5).

A scheduled corpus asset (``gap_scan`` / ``retrieval_eval`` / ``catalog_sync``)
must be re-materialized on a wall-clock cadence: «ассет должен обновляться по
часам, а не по апстриму». This is *distinct* from asset staleness (§9.8), which
compares an asset to its upstream inputs. Here we only ask: how long ago was the
asset materialized, and does that exceed the allowed lag?

The SLA is a single number — :class:`FreshnessPolicy.maximum_lag_minutes`, the
maximum wall-clock lag «допустимое отставание в минутах» between successive
materializations. Everything is a pure function of caller-supplied epochs; no
store, no ``time.time()`` — «время передаёт вызывающий».

* :func:`minutes_late`      — ``max(0, age_minutes - lag)``; a never-materialized
  asset (``last is None``) is infinitely late.
* :func:`is_overdue`        — ``minutes_late(...) > 0``.
* :func:`next_deadline_epoch` — ``last + lag * 60``, the epoch by which the next
  materialization is due.

Public API:

* :class:`FreshnessPolicy`   — frozen SLA with :meth:`FreshnessPolicy.as_dict`.
* :func:`minutes_late`       — minutes past the deadline (``inf`` if never built).
* :func:`is_overdue`         — overdue predicate.
* :func:`next_deadline_epoch` — epoch of the next materialization deadline.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FreshnessPolicy",
    "is_overdue",
    "minutes_late",
    "next_deadline_epoch",
]

_SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Immutable wall-clock freshness SLA — неизменяемый SLA свежести (§9.5).

    ``maximum_lag_minutes`` is the largest wall-clock lag «допустимое отставание»
    tolerated between successive materializations. Must be strictly positive — a
    zero or negative lag has no meaningful deadline.
    """

    maximum_lag_minutes: float

    def __post_init__(self) -> None:
        """Reject non-positive lag — отвергаем неположительное отставание (§9.5)."""
        if self.maximum_lag_minutes <= 0:
            raise ValueError("maximum_lag_minutes must be positive")

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — политика как словарь (§9.5)."""
        return {"maximum_lag_minutes": self.maximum_lag_minutes}


def minutes_late(
    last_materialized_epoch: float | None,
    now_epoch: float,
    policy: FreshnessPolicy,
) -> float:
    """Minutes past the freshness deadline — минуты просрочки (§9.5).

    Returns ``max(0, age_minutes - lag)`` where ``age_minutes`` is the wall-clock
    age of the last materialization in minutes. A never-materialized asset
    (``last_materialized_epoch is None``) is treated as infinitely late — «никогда
    не строился — бесконечно просрочен».
    """
    if last_materialized_epoch is None:
        return float("inf")
    age_minutes = (now_epoch - last_materialized_epoch) / _SECONDS_PER_MINUTE
    return max(0.0, age_minutes - policy.maximum_lag_minutes)


def is_overdue(
    last_materialized_epoch: float | None,
    now_epoch: float,
    policy: FreshnessPolicy,
) -> bool:
    """Is the asset overdue? — просрочен ли ассет? (§9.5).

    ``True`` iff :func:`minutes_late` is strictly greater than zero. Exactly at
    the deadline (``now == last + lag * 60``) the asset is *not* overdue.
    """
    return minutes_late(last_materialized_epoch, now_epoch, policy) > 0.0


def next_deadline_epoch(
    last_materialized_epoch: float,
    policy: FreshnessPolicy,
) -> float:
    """Epoch of the next materialization deadline — эпоха следующего дедлайна (§9.5).

    Returns ``last_materialized_epoch + maximum_lag_minutes * 60`` — the wall-clock
    instant by which the next materialization is due.
    """
    return last_materialized_epoch + policy.maximum_lag_minutes * _SECONDS_PER_MINUTE
