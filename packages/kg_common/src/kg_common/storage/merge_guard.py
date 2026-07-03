"""Action ``merge``: guard конфликтующих verified-полей — merge conflict guard (§16.6).

When two (or more) entities are merged into one canonical node, human-verified facts
must not be silently reconciled away. If entity A is verified on ``value=5`` and entity B
is verified on ``value=7``, the machine cannot pick a winner — a merge would destroy a
human-verified fact. This guard inspects the entities' ``verified_fields`` lists and
refuses the merge (``allowed=False``) when a field verified on two different entities
carries differing values, unless the caller explicitly passes ``override=True`` (a
deliberate human decision), in which case the merge proceeds but the conflicting fields
are still reported for the audit trail.

Поведение / behaviour:

* A field is *considered* only if it appears in some entity's ``verified_fields`` list.
* A field is a *conflict* when at least two entities that verify it disagree on its
  value. A field verified on only one entity is never a conflict (nothing to disagree
  with). Multiple entities that verify a field but all agree on the value — no conflict.
* ``override=True`` forces ``allowed=True`` yet still populates ``conflicting_fields``.

The guard is pure and backend-agnostic. :func:`canonical_id` picks the surviving node id
(highest ``degree``, ties broken by lexicographically smallest id).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MergeCheck:
    """Outcome of a verified-field conflict check for a ``merge`` action (§16.6).

    :param allowed: whether the merge may proceed (False on unresolved conflict).
    :param conflicting_fields: verified fields whose values disagree across entities.
    :param reason: human-readable explanation — пояснение для аудита.
    """

    allowed: bool
    conflicting_fields: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view — сериализуемое представление результата."""
        return asdict(self)


def _verified_values(
    entities: Sequence[Mapping[str, Any]],
    name: str,
) -> list[Any]:
    """Collect values of ``name`` from entities that list it in ``verified_fields``."""
    values: list[Any] = []
    for entity in entities:
        verified = entity.get("verified_fields") or []
        if name in verified:
            values.append(entity.get(name))
    return values


def check_merge(
    entities: Sequence[Mapping[str, Any]],
    override: bool = False,
) -> MergeCheck:
    """Check whether ``entities`` may be merged without clobbering verified facts (§16.6).

    Every field that appears in any entity's ``verified_fields`` list is inspected. A
    field is a conflict when at least two entities verify it with differing values. The
    merge is disallowed on any conflict unless ``override`` is True, which forces
    ``allowed=True`` while still reporting the conflicting fields for the audit trail.
    """
    candidate_fields: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        for name in entity.get("verified_fields") or []:
            if name not in seen:
                seen.add(name)
                candidate_fields.append(name)

    conflicting: list[str] = []
    for name in candidate_fields:
        values = _verified_values(entities, name)
        if len(values) < 2:
            continue
        first = values[0]
        if any(other != first for other in values[1:]):
            conflicting.append(name)

    if not conflicting:
        return MergeCheck(allowed=True, conflicting_fields=[], reason="no verified-field conflicts")

    joined = ", ".join(conflicting)
    if override:
        reason = f"override: merged despite verified-field conflicts on {joined}"
        return MergeCheck(allowed=True, conflicting_fields=conflicting, reason=reason)
    reason = f"blocked: verified-field conflicts on {joined}"
    return MergeCheck(allowed=False, conflicting_fields=conflicting, reason=reason)


def canonical_id(entities: Sequence[Mapping[str, Any]]) -> str:
    """Return the surviving node id — highest ``degree``, ties → smallest id (§16.6)."""
    if not entities:
        raise ValueError("canonical_id requires at least one entity")
    best = min(
        entities,
        key=lambda e: (-int(e.get("degree", 0)), str(e.get("id"))),
    )
    return str(best.get("id"))
