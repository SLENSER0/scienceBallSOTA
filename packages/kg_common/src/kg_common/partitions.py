"""Dagster-style partitioning helpers — партиционирование запусков (§9.3).

Pure-python re-implementation of the *partitioning* idea that orchestrators such
as Dagster expose, **without taking a dependency on Dagster** (§9.3). A pipeline
run is sliced into independent *partitions* — per document, per source, or per
calendar month — so backfills and incremental runs address exactly one slice by
its key («ключ партиции»).

Everything here is deterministic and side-effect free:

* No wall-clock — :func:`monthly_partitions` takes an *explicit* start
  ``(year, month)`` instead of reading ``datetime.now`` (§9.3 «детерминизм»).
* Keys are order-preserving де-дублированы, so repeated inputs collapse to one
  partition while the first-seen order is kept.

Public API:

* :class:`PartitionSet`        — frozen, named, de-duplicated key set with
  :meth:`PartitionSet.as_dict`.
* :func:`partition_key_for`    — stable slug for a document / source id.
* :func:`static_partitions`    — wrap an explicit list of keys.
* :func:`by_document_partition`/:func:`by_source_partition` — one key per id.
* :func:`monthly_partitions`   — ``n`` sequential ``YYYY-MM`` keys from a start.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from kg_common.ids import slugify

__all__ = [
    "PartitionSet",
    "by_document_partition",
    "by_source_partition",
    "monthly_partitions",
    "partition_key_for",
    "static_partitions",
]


def _dedup(keys: Iterable[str]) -> tuple[str, ...]:
    """Order-preserving de-duplication — уникальные ключи в порядке появления (§9.3)."""
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class PartitionSet:
    """Immutable, named set of partition keys — набор партиций (§9.3).

    ``name`` identifies the partitioning scheme (``"by_document"``, ``"monthly"``,
    …); ``keys`` are the ordered, de-duplicated partition keys. Constructed via the
    builder functions below rather than directly, but the container itself is a
    plain frozen record so it can be hashed, compared and serialized.
    """

    name: str
    keys: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — таблица «имя + список ключей» (§9.3)."""
        return {"name": self.name, "keys": list(self.keys)}


def partition_key_for(doc_id: str) -> str:
    """Stable partition slug for a document / source id — стабильный ключ (§9.3).

    Deterministic: the same ``doc_id`` always yields the same key, and the key is
    a filesystem-/url-safe slug (lowercase, dashes) via :func:`kg_common.ids.slugify`.
    ``partition_key_for("doc:Al-Cu 2024") == "doc-al-cu-2024"``.
    """
    return slugify(doc_id)


def static_partitions(keys: Iterable[str], *, name: str = "static") -> PartitionSet:
    """Wrap an explicit list of keys as a :class:`PartitionSet` — статические партиции (§9.3).

    Keys are taken verbatim (no slugging) but de-duplicated in first-seen order.
    """
    return PartitionSet(name=name, keys=_dedup(keys))


def by_document_partition(doc_ids: Iterable[str]) -> PartitionSet:
    """One partition per document — партиции по документам (§9.3).

    Each ``doc_id`` is mapped through :func:`partition_key_for`, then de-duplicated.
    """
    return PartitionSet(name="by_document", keys=_dedup(partition_key_for(d) for d in doc_ids))


def by_source_partition(source_ids: Iterable[str]) -> PartitionSet:
    """One partition per source — партиции по источникам (§9.3).

    Mirrors :func:`by_document_partition` for source-level backfills.
    """
    return PartitionSet(name="by_source", keys=_dedup(partition_key_for(s) for s in source_ids))


def monthly_partitions(
    start_year: int,
    start_month: int,
    n: int,
    *,
    name: str = "monthly",
) -> PartitionSet:
    """``n`` sequential ``YYYY-MM`` partition keys from an explicit start — месяцы (§9.3).

    Generates keys deterministically starting at ``(start_year, start_month)`` and
    advancing one calendar month at a time, wrapping December → January and bumping
    the year. **No** ``datetime.now`` is consulted — the start is always explicit
    (§9.3 «детерминизм»). ``monthly_partitions(2023, 11, 4)`` →
    ``("2023-11", "2023-12", "2024-01", "2024-02")``.

    ``start_month`` must be in ``1..12`` and ``n`` must be ``>= 0``.
    """
    if not 1 <= start_month <= 12:
        raise ValueError("start_month must be in 1..12")
    if n < 0:
        raise ValueError("n must be >= 0")
    keys: list[str] = []
    year, month = start_year, start_month
    for _ in range(n):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return PartitionSet(name=name, keys=tuple(keys))
