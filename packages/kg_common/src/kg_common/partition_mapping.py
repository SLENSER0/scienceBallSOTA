"""Partition mapping — маппинг партиций между ассетами (§9.3).

A tiny, deterministic layer that answers a single scheduling question: given a
*downstream* partition key and the *universe* of upstream partition keys, which
upstream partitions does it depend on? Three ``PartitionMapping`` kinds cover
every dependency in the asset graph:

* ``identity``    — 1:1 mapping. Партиция «doc-1» downstream зависит от «doc-1»
  upstream, но только если та существует в universe (иначе — пустая связь).
* ``all``         — fan-in. Downstream зависит от *всех* upstream партиций в
  порядке universe (used by ``gap_scan`` / ``retrieval_eval`` aggregates).
* ``time_to_day`` — time-window rollup. Месячная downstream партиция «2026-07»
  зависит от всех дневных upstream партиций того же месяца.

Everything is side-effect free and order-preserving: ``all`` and ``time_to_day``
keep the universe's own ordering so runs are reproducible.

Public API:

* :class:`PartitionDependency` — frozen result with :meth:`as_dict`.
* :func:`day_to_month`         — ``'2026-07-03' -> '2026-07'``.
* :func:`resolve_dependency`   — resolve a mapping ``kind`` to a dependency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "PartitionDependency",
    "day_to_month",
    "resolve_dependency",
]

# Valid mapping kinds — допустимые виды маппинга.
_KINDS = frozenset({"identity", "all", "time_to_day"})


@dataclass(frozen=True, slots=True)
class PartitionDependency:
    """Resolved upstream dependency for one downstream partition key.

    Frozen result — связь downstream-партиции с её upstream-партициями.

    Attributes:
        downstream_key: The downstream partition being resolved — целевая
            партиция.
        upstream_keys: Ordered upstream partition keys it depends on; empty
            tuple means no dependency — зависимые upstream-партиции.
    """

    downstream_key: str
    upstream_keys: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view — JSON-представление связи."""
        return {
            "downstream_key": self.downstream_key,
            "upstream_keys": list(self.upstream_keys),
        }


def day_to_month(day_key: str) -> str:
    """Map a day partition key to its month key — день -> месяц.

    ``'2026-07-03' -> '2026-07'``. Expects an ISO ``YYYY-MM-DD`` day key and
    returns the ``YYYY-MM`` month prefix.

    Args:
        day_key: ISO day partition key, ``YYYY-MM-DD``.

    Returns:
        The ``YYYY-MM`` month prefix.

    Raises:
        ValueError: If ``day_key`` is not in ``YYYY-MM-DD`` form.
    """
    parts = day_key.split("-")
    if len(parts) != 3 or not all(parts):
        msg = f"invalid day partition key: {day_key!r} (expected YYYY-MM-DD)"
        raise ValueError(msg)
    year, month, _day = parts
    return f"{year}-{month}"


def resolve_dependency(
    kind: str,
    downstream_key: str,
    upstream_universe: Sequence[str],
) -> PartitionDependency:
    """Resolve a partition mapping to a concrete dependency — разрешить маппинг.

    Args:
        kind: Mapping kind, one of ``{'identity', 'all', 'time_to_day'}``.
        downstream_key: The downstream partition key being resolved.
        upstream_universe: All available upstream partition keys, in the order
            they should be consumed — вся вселенная upstream-партиций.

    Returns:
        A :class:`PartitionDependency` whose ``upstream_keys`` is order-preserved
        relative to ``upstream_universe``.

    Raises:
        ValueError: If ``kind`` is not a known mapping kind.
    """
    if kind not in _KINDS:
        msg = f"unknown partition mapping kind: {kind!r} (expected one of {sorted(_KINDS)})"
        raise ValueError(msg)

    if kind == "identity":
        # 1:1 — depend on the matching upstream key iff it exists in universe.
        present = downstream_key in upstream_universe
        upstream = (downstream_key,) if present else ()
    elif kind == "all":
        # Fan-in — depend on the whole universe, order preserved.
        upstream = tuple(upstream_universe)
    else:  # kind == "time_to_day"
        # Rollup — select day keys whose month equals the downstream month.
        upstream = tuple(
            day_key for day_key in upstream_universe if day_to_month(day_key) == downstream_key
        )

    return PartitionDependency(downstream_key=downstream_key, upstream_keys=upstream)
