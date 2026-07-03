"""Contradictions rolled up by material / property (§15.4, §5.2.7).

Свёртка противоречий по материалу и свойству — pure-python aggregation over the
``Contradiction`` records surfaced by §15.4 (:mod:`kg_retrievers.contradiction_detector`).
§5.2.7 asks the answer layer for a *contradictions-by-material/property* rollup so a
reader sees, per (material, property) pair, **how many** conflicting measurements
exist, **how bad** the worst one is, **which mechanisms** are at play, and a pointer
to the single worst record.

This is distinct from :mod:`kg_retrievers.gap_clustering` (§15.12), which clusters
generic ``Gap`` nodes by a fallback key — here we group real ``Contradiction``
records and aggregate their numeric divergence and subtypes.

Each input contradiction is a plain dict with the keys ``id``, ``material_id``,
``property_id`` (or ``property_name``), ``relative_diff``, ``contradiction_subtype``
and ``measurement_ids``. Missing / malformed fields degrade gracefully (blank
material/property, ``0.0`` divergence, no subtype). The module never touches the
graph store; results are frozen dataclasses exposing ``as_dict()`` for JSON
transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "ContradictionGroup",
    "cluster_contradictions",
    "most_conflicted",
]

# A raw Contradiction record dict as produced upstream (§15.4).
Contradiction = dict[str, Any]


@dataclass(frozen=True)
class ContradictionGroup:
    """All contradictions on one (material, property) pair, aggregated (§5.2.7).

    ``material_id`` / ``property_name`` identify the pair (property_name carries the
    ``property_id`` when present, else the free-text ``property_name``). ``count`` is
    the number of contradiction records in the group; ``max_relative_diff`` is the
    largest ``relative_diff`` among them (наибольшее расхождение). ``subtypes`` is the
    sorted, de-duplicated set of ``contradiction_subtype`` values; ``measurement_ids``
    is the sorted union of every group member's measurement ids. ``worst_id`` is the
    ``id`` of the record with the highest ``relative_diff`` (худшая запись).
    """

    material_id: str
    property_name: str
    count: int
    max_relative_diff: float
    subtypes: tuple[str, ...]
    measurement_ids: tuple[str, ...]
    worst_id: str

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "property_name": self.property_name,
            "count": self.count,
            "max_relative_diff": self.max_relative_diff,
            "subtypes": list(self.subtypes),
            "measurement_ids": list(self.measurement_ids),
            "worst_id": self.worst_id,
        }


def _text(value: object) -> str:
    """A trimmed non-empty string, else ``""`` for ``None`` / non-str / blank."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _as_float(value: Any) -> float:
    """Coerce ``value`` to ``float`` (``bool`` and non-numerics → ``0.0``)."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _property_key(record: Contradiction) -> str:
    """Property identity: ``property_id`` if present, иначе ``property_name``."""
    return _text(record.get("property_id")) or _text(record.get("property_name"))


def _measurement_ids(record: Contradiction) -> list[str]:
    """The record's measurement ids as a list of trimmed non-empty strings."""
    raw = record.get("measurement_ids")
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return []
    return [t for t in (_text(m) for m in raw) if t]


def cluster_contradictions(contradictions: list[Contradiction]) -> list[ContradictionGroup]:
    """Group contradictions by (material, property) and aggregate them (§5.2.7).

    Records bucket on ``(material_id, property_id-or-property_name)``. For each bucket
    the group carries ``count`` (member count), ``max_relative_diff`` (largest member
    divergence), ``subtypes`` (sorted de-duped ``contradiction_subtype`` set),
    ``measurement_ids`` (sorted union across members) and ``worst_id`` (the ``id`` of
    the member with the highest ``relative_diff``). Groups come out sorted by ``count``
    descending, then ``max_relative_diff`` descending. ``[]`` → ``[]``.
    """
    buckets: dict[tuple[str, str], list[Contradiction]] = {}
    for record in contradictions:
        key = (_text(record.get("material_id")), _property_key(record))
        buckets.setdefault(key, []).append(record)

    groups: list[ContradictionGroup] = []
    for (material_id, property_name), members in buckets.items():
        subtypes = {st for st in (_text(m.get("contradiction_subtype")) for m in members) if st}
        measurement_ids: set[str] = set()
        for member in members:
            measurement_ids.update(_measurement_ids(member))
        worst = max(members, key=lambda m: _as_float(m.get("relative_diff")))
        groups.append(
            ContradictionGroup(
                material_id=material_id,
                property_name=property_name,
                count=len(members),
                max_relative_diff=_as_float(worst.get("relative_diff")),
                subtypes=tuple(sorted(subtypes)),
                measurement_ids=tuple(sorted(measurement_ids)),
                worst_id=_text(worst.get("id")),
            )
        )

    groups.sort(key=lambda g: (g.count, g.max_relative_diff), reverse=True)
    return groups


def most_conflicted(groups: list[ContradictionGroup]) -> ContradictionGroup | None:
    """Return the highest-``count`` group, ties broken by ``max_relative_diff``.

    Наиболее конфликтная пара материал/свойство. Returns ``None`` for empty input.
    """
    if not groups:
        return None
    return max(groups, key=lambda g: (g.count, g.max_relative_diff))
