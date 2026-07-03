"""Community hierarchy roll-up aggregation (§11.6 агрегация свёрткой иерархии).

Rolls each *leaf* community's own members and documents **up** an arbitrary
N-level parent map to every ancestor. This is a distinct aggregation step:

* :mod:`kg_retrievers.community_hierarchy` *builds* a two-level structure but
  does not aggregate descendant sets past a single split;
* :mod:`kg_retrievers.community_membership_index` provides a *reverse*
  per-level member→community lookup, not an upward union.

Given ``own_members`` (per-community direct members), a ``parent_of`` map of
arbitrary depth, and optional ``docs_of`` (per-community documents), the roll-up
computes for every community the union of its own set with those of *all* of its
descendants (транзитивное замыкание вниз). The traversal is cycle-safe: a
``visited`` set guards against malformed parent maps that form a loop.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RolledCommunity:
    """Aggregated view of one community after descendant roll-up (§11.6).

    ``own_members`` are the community's direct members; ``all_members`` /
    ``all_docs`` additionally include every descendant's members / documents.
    ``subtree_size`` is ``len(all_members)`` — the number of distinct members in
    the community's subtree (число уникальных участников в поддереве).
    """

    community_id: int
    own_members: tuple[str, ...]
    all_members: tuple[str, ...]
    all_docs: tuple[str, ...]
    subtree_size: int

    def as_dict(self) -> dict:
        return {
            "community_id": self.community_id,
            "own_members": sorted(self.own_members),
            "all_members": sorted(self.all_members),
            "all_docs": sorted(self.all_docs),
            "subtree_size": self.subtree_size,
        }


def _children_of(parent_of: Mapping[int, int]) -> dict[int, list[int]]:
    """Invert ``parent_of`` into a child→ list-of-children адъяcency map."""
    children: dict[int, list[int]] = {}
    for child, parent in parent_of.items():
        children.setdefault(parent, []).append(child)
    return children


def rollup(
    own_members: Mapping[int, Iterable[str]],
    parent_of: Mapping[int, int],
    docs_of: Mapping[int, Iterable[str]] | None = None,
) -> dict[int, RolledCommunity]:
    """Roll leaf member/document sets up ``parent_of`` to every ancestor (§11.6).

    Every community mentioned in ``own_members``, ``parent_of`` (as child or
    parent) or ``docs_of`` gets a :class:`RolledCommunity`. Each community's
    ``all_members`` / ``all_docs`` union its own sets with those of all its
    descendants. Cycle-safe via a ``visited`` set.
    """
    docs_of = docs_of or {}

    # Собираем полный набор community_id из всех входных карт.
    ids: set[int] = set(own_members) | set(docs_of)
    for child, parent in parent_of.items():
        ids.add(child)
        ids.add(parent)

    children = _children_of(parent_of)

    def _own_members(cid: int) -> set[str]:
        return set(own_members.get(cid, ()))

    def _own_docs(cid: int) -> set[str]:
        return set(docs_of.get(cid, ()))

    def _accumulate(cid: int, visited: set[int]) -> tuple[set[str], set[str]]:
        """Union of ``cid`` and its descendants' members and docs."""
        if cid in visited:  # защита от циклов в parent_of
            return set(), set()
        visited.add(cid)
        members = _own_members(cid)
        docs = _own_docs(cid)
        for child in children.get(cid, ()):
            sub_members, sub_docs = _accumulate(child, visited)
            members |= sub_members
            docs |= sub_docs
        return members, docs

    result: dict[int, RolledCommunity] = {}
    for cid in ids:
        all_members, all_docs = _accumulate(cid, set())
        result[cid] = RolledCommunity(
            community_id=cid,
            own_members=tuple(sorted(_own_members(cid))),
            all_members=tuple(sorted(all_members)),
            all_docs=tuple(sorted(all_docs)),
            subtree_size=len(all_members),
        )
    return result
