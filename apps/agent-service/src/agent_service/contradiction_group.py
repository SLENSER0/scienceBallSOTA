"""§13.16 узел verifier — группировка противоречий / contradiction grouping.

The §13.16 ``verifier`` node's contradiction check and the §5.2.2 Contradictions
tab both need the same thing: measurements that report divergent values for one
and the same ``(material, regime, property)`` key. This module folds a raw list
of measurement dicts into frozen :class:`ContradictionGroup` objects.

:func:`group_contradictions` buckets measurements by their
``(material, regime, property)`` key and emits a group only when that bucket
holds **two or more distinct values** (identical readings are agreement, not a
contradiction). Each emitted group carries the deduped+sorted values, the value
``spread`` (``max - min``), and the deduped+sorted contributing ``source_ids``.
Groups come back sorted by ``spread`` descending so the worst conflict surfaces
first. :func:`has_contradictions` is a thin truthiness helper over the result.

Deterministic and dependency-free — the graph reads that produce these raw
measurement dicts live in the §11 tool layer, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContradictionGroup:
    """§13.16 группа противоречий / one conflicting-measurement group.

    Identifies a single ``(material, regime, property)`` key that carries
    divergent values. ``values`` is the deduped+sorted tuple of readings,
    ``spread`` is ``max - min`` over those values, and ``source_ids`` is the
    deduped+sorted tuple of sources that contributed to the conflict.
    """

    material: str
    regime: str
    property: str
    values: tuple[float, ...]
    spread: float
    source_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the §5.2.2 tab (JSON-friendly / для сериализации).

        ``values`` and ``source_ids`` are emitted as lists rather than tuples.
        """
        return {
            "material": self.material,
            "regime": self.regime,
            "property": self.property,
            "values": list(self.values),
            "spread": self.spread,
            "source_ids": list(self.source_ids),
        }


def group_contradictions(measurements: list[dict]) -> list[ContradictionGroup]:
    """Group divergent measurements into :class:`ContradictionGroup` objects.

    Each measurement dict provides ``material``, ``regime``, ``property``,
    ``value`` and ``source_id``. Measurements are bucketed by their
    ``(material, regime, property)`` key. A bucket yields a group only when it
    holds **>= 2 distinct values**; ``spread`` is ``max - min`` over the distinct
    values, ``source_ids`` are deduplicated and sorted. The returned list is
    sorted by ``spread`` descending (ties broken by key ascending).
    """
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for m in measurements:
        key = (str(m["material"]), str(m["regime"]), str(m["property"]))
        bucket = buckets.setdefault(key, {"values": set(), "source_ids": set()})
        bucket["values"].add(float(m["value"]))
        bucket["source_ids"].add(str(m["source_id"]))

    groups: list[ContradictionGroup] = []
    for (material, regime, property_), bucket in buckets.items():
        values = tuple(sorted(bucket["values"]))
        if len(values) < 2:
            continue
        groups.append(
            ContradictionGroup(
                material=material,
                regime=regime,
                property=property_,
                values=values,
                spread=values[-1] - values[0],
                source_ids=tuple(sorted(bucket["source_ids"])),
            )
        )

    groups.sort(key=lambda g: (-g.spread, g.material, g.regime, g.property))
    return groups


def has_contradictions(groups: list[ContradictionGroup]) -> bool:
    """``True`` iff ``groups`` is non-empty (см. §13.16 verifier gate)."""
    return bool(groups)
