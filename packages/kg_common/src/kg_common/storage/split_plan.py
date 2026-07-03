"""Redistribution planner for the §16.6 ``split`` action (RU/EN).

Чистый планировщик (pure planner) — вычисляет, куда попадёт каждое ребро и
свидетельство при разбиении (split) исходной сущности на несколько новых, но
**не выполняет** никаких записей в граф. This lets the split action be
previewed, validated and diffed before any Kuzu write happens.

A ``partition`` maps every *new* entity id to the list of edge/evidence ids it
should receive. Any element not named in a bucket lands in ``unassigned``; an
id claimed by two buckets is a conflict and raises ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def _id_of(element: Mapping) -> str:
    """Return the identifier of an edge/evidence mapping (``id`` key)."""
    return str(element["id"])


@dataclass(frozen=True)
class SplitPlan:
    """Planned redistribution for one ``split`` action (§16.6).

    План перераспределения: какое ребро/свидетельство уходит к какой новой
    сущности. ``edge_assignments`` / ``evidence_assignments`` map an element id
    to the new entity id that receives it; ``unassigned`` lists ids that no
    partition bucket claimed (they stay unattached / require manual routing).
    """

    source_id: str
    new_ids: tuple[str, ...]
    edge_assignments: Mapping[str, str]
    evidence_assignments: Mapping[str, str]
    unassigned: tuple[str, ...]

    def as_dict(self) -> dict:
        """Return a JSON-friendly plain-``dict`` view (сериализуемый вид)."""
        return {
            "source_id": self.source_id,
            "new_ids": list(self.new_ids),
            "edge_assignments": dict(self.edge_assignments),
            "evidence_assignments": dict(self.evidence_assignments),
            "unassigned": list(self.unassigned),
        }


def plan_split(
    source_id: str,
    new_ids: Sequence[str],
    edges: Sequence[Mapping],
    evidences: Sequence[Mapping],
    partition: Mapping[str, Sequence[str]],
) -> SplitPlan:
    """Compute a :class:`SplitPlan` for splitting ``source_id`` (§16.6).

    ``partition`` maps each new entity id to the edge/evidence ids it should
    receive. Разбиение (split) требует минимум двух новых сущностей.

    Raises:
        ValueError: if ``len(new_ids) < 2``, or if a single edge/evidence id is
            claimed by more than one partition bucket (конфликт назначения).
    """
    if len(new_ids) < 2:
        raise ValueError(f"split requires >=2 new_ids, got {len(new_ids)} (§16.6)")

    # Build id -> new_id, detecting double-claims across buckets.
    owner: dict[str, str] = {}
    for new_id in new_ids:
        for element_id in partition.get(new_id, ()):  # type: ignore[arg-type]
            key = str(element_id)
            if key in owner and owner[key] != new_id:
                raise ValueError(
                    f"element {key!r} claimed by both {owner[key]!r} and {new_id!r} (§16.6)"
                )
            owner[key] = new_id

    edge_assignments: dict[str, str] = {}
    evidence_assignments: dict[str, str] = {}
    unassigned: list[str] = []

    for edge in edges:
        eid = _id_of(edge)
        if eid in owner:
            edge_assignments[eid] = owner[eid]
        else:
            unassigned.append(eid)

    for evidence in evidences:
        vid = _id_of(evidence)
        if vid in owner:
            evidence_assignments[vid] = owner[vid]
        else:
            unassigned.append(vid)

    return SplitPlan(
        source_id=source_id,
        new_ids=tuple(new_ids),
        edge_assignments=edge_assignments,
        evidence_assignments=evidence_assignments,
        unassigned=tuple(unassigned),
    )
