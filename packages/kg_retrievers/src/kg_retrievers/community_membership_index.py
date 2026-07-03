"""Entity→community reverse membership index for GraphRAG (§11.6).

GraphRAG assigns every entity to a community at each hierarchy *level*. The
forward direction (community → members) is what detection produces; retrieval
often needs the reverse: *given an entity, which community does it belong to at
level L, and who are its co-members?* This module builds that reverse index —
обратный индекс принадлежности — as a pure-python, frozen structure with no
store dependency.

An assignment is a ``(entity_id, level, community_id)`` triple. The same entity
may sit in different communities at different levels (a leaf cluster at level 0,
a coarser super-community at level 1), so ``community_at`` is keyed on both the
entity and the level. ``members`` and ``co_members`` answer the neighbourhood
questions used by community-aware ranking and expansion.

RU/EN entity ids pass through verbatim — no tokenization here, just membership.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger

_log = get_logger("community_membership_index")


@dataclass(frozen=True)
class MembershipIndex:
    """Immutable entity→community reverse index (§11.6).

    - ``assignments``: sorted, de-duplicated ``(entity_id, level, community_id)``
      triples — the full membership table / таблица принадлежности.
    """

    assignments: tuple[tuple[str, int, int], ...]

    def as_dict(self) -> dict:
        return {"n_assignments": len(self.assignments)}

    # -- build ---------------------------------------------------------------
    @classmethod
    def from_assignments(cls, rows: list[dict]) -> MembershipIndex:
        """Build the index from ``{entity_id, level, community_id}`` rows.

        Triples are sorted and de-duplicated so two calls with the same rows in
        any order yield an identical (frozen) index. Rows are read by key, not
        position, so extra keys are ignored.
        """
        triples = {(str(r["entity_id"]), int(r["level"]), int(r["community_id"])) for r in rows}
        idx = cls(assignments=tuple(sorted(triples)))
        _log.info("community_membership_index.build", **idx.as_dict())
        return idx

    # -- query ---------------------------------------------------------------
    def community_at(self, entity_id: str, level: int) -> int | None:
        """Community id of *entity_id* at *level*, or ``None`` if unassigned.

        An entity typically belongs to exactly one community per level; the
        first matching triple (assignments are sorted) is returned.
        """
        for eid, lvl, cid in self.assignments:
            if eid == entity_id and lvl == level:
                return cid
        return None

    def members(self, level: int, community_id: int) -> tuple[str, ...]:
        """Sorted, unique entity ids in ``community_id`` at *level* (``()`` if none)."""
        found = {eid for eid, lvl, cid in self.assignments if lvl == level and cid == community_id}
        return tuple(sorted(found))

    def co_members(self, entity_id: str, level: int) -> tuple[str, ...]:
        """Sorted co-members of *entity_id* at *level*, excluding itself.

        Returns ``()`` when the entity is unassigned at *level* or is the sole
        member of its community (одиночка).
        """
        cid = self.community_at(entity_id, level)
        if cid is None:
            return ()
        return tuple(m for m in self.members(level, cid) if m != entity_id)
