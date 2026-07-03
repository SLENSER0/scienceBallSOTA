"""Hierarchical (multi-level) community structure (§11.6 иерархия сообществ).

Builds a two-level community hierarchy on top of the flat GraphRAG community
detection (see :mod:`kg_retrievers.community`). A coarse modularity sweep yields
level-0 *super-communities* (крупные кластеры); each is then re-partitioned on
its induced subgraph at a higher resolution into level-1 *sub-communities*
(подкластеры), nested strictly inside their parent. Because every fine partition
is computed on the parent's induced subgraph, a sub-community's members are a
subset of its parent's members *by construction*.

If a super-community cannot be split further (a single fine partition results,
e.g. on a tiny graph) it stays a level-0 leaf and no redundant level-1 node is
emitted — the structure degrades gracefully to level-0 only.

Uses :func:`networkx.community.greedy_modularity_communities`, the same detector
the flat :func:`kg_retrievers.community.detect_communities` uses, so the two
views stay consistent. This module never mutates the store — it only reads the
entity projection and returns an in-memory :class:`CommunityHierarchy`.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

_log = get_logger("community_hierarchy")

# Modularity resolutions for the two-level sweep (§11.6). Higher resolution
# favours more, smaller communities (finer partition); lower favours fewer,
# larger ones (coarser partition).
_COARSE_RESOLUTION = 1.0  # level-0 super-communities (крупные кластеры)
_FINE_RESOLUTION = 2.0  # level-1 sub-communities (подкластеры)


@dataclass(frozen=True)
class HierarchyNode:
    """One community in the hierarchy (§11.6).

    ``level`` 0 = coarse super-community, 1 = fine sub-community. A level-1 node
    carries ``parent_id`` = the ``community_id`` of the level-0 node that
    contains it; a level-0 node has ``parent_id = None``.
    """

    level: int
    community_id: str
    member_ids: tuple[str, ...]
    parent_id: str | None
    size: int

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "community_id": self.community_id,
            "member_ids": list(self.member_ids),
            "parent_id": self.parent_id,
            "size": self.size,
        }


@dataclass(frozen=True)
class CommunityHierarchy:
    """A nested community structure over the entity graph (§11.6).

    ``nodes`` holds a flat list of every :class:`HierarchyNode` (both levels);
    parent/child links are recovered via ``parent_id``. ``levels`` records how
    many levels were requested (a graph may still degrade to level-0 only).
    """

    nodes: tuple[HierarchyNode, ...] = ()
    levels: int = 2

    # -- lookups ---------------------------------------------------------
    def node(self, community_id: str) -> HierarchyNode | None:
        """Return the :class:`HierarchyNode` for ``community_id`` (or None)."""
        for hn in self.nodes:
            if hn.community_id == community_id:
                return hn
        return None

    def at_level(self, level: int) -> list[HierarchyNode]:
        """All nodes at a given hierarchy level."""
        return [hn for hn in self.nodes if hn.level == level]

    def parent_of(self, community_id: str) -> str | None:
        """``community_id`` of the parent super-community, or None if a root."""
        hn = self.node(community_id)
        return hn.parent_id if hn else None

    def children_of(self, community_id: str) -> list[str]:
        """``community_id``s of the sub-communities nested in ``community_id``."""
        return [hn.community_id for hn in self.nodes if hn.parent_id == community_id]

    # -- serialisation ---------------------------------------------------
    def as_dict(self) -> dict:
        """Serialise the whole structure as a nested tree (§11.6)."""
        by_parent: dict[str | None, list[HierarchyNode]] = {}
        for hn in self.nodes:
            by_parent.setdefault(hn.parent_id, []).append(hn)
        roots = by_parent.get(None, [])
        return {
            "levels": self.levels,
            "n_nodes": len(self.nodes),
            "n_roots": len(roots),
            "tree": [self._subtree(r, by_parent) for r in roots],
        }

    @staticmethod
    def _subtree(hn: HierarchyNode, by_parent: dict[str | None, list[HierarchyNode]]) -> dict:
        node = hn.as_dict()
        node["children"] = [
            CommunityHierarchy._subtree(c, by_parent) for c in by_parent.get(hn.community_id, [])
        ]
        return node


def _project_entity_graph(store: KuzuGraphStore, nx) -> object:  # type: ignore[no-untyped-def]
    """Undirected projection over :Entity nodes (same as §11 detect)."""
    labels = list(ENTITY_LABELS)
    rows = store.rows(
        "MATCH (a:Node)-[:Rel]-(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id",
        {"l": labels},
    )
    graph = nx.Graph()
    graph.add_edges_from((a, b) for a, b in rows if a != b)
    return graph


def _detect(nx, graph: object, resolution: float) -> list[set]:  # type: ignore[no-untyped-def]
    """Modularity communities, largest first; graceful on edgeless graphs."""
    if graph.number_of_nodes() == 0:  # type: ignore[attr-defined]
        return []
    if graph.number_of_edges() == 0:  # type: ignore[attr-defined]
        return [{n} for n in graph.nodes()]  # type: ignore[attr-defined]
    comms = nx.community.greedy_modularity_communities(graph, resolution=resolution)
    return sorted((set(c) for c in comms), key=len, reverse=True)


def build_hierarchy(store: KuzuGraphStore, *, levels: int = 2) -> CommunityHierarchy:
    """Build a ``levels``-deep community hierarchy over the entity graph (§11.6).

    ``levels=1`` returns the coarse partition only; ``levels>=2`` additionally
    splits each super-community into nested sub-communities. Read-only: the
    store is never mutated.
    """
    import networkx as nx

    graph = _project_entity_graph(store, nx)
    if graph.number_of_nodes() == 0:  # type: ignore[attr-defined]
        _log.info("community_hierarchy.build", n_nodes=0, levels=levels)
        return CommunityHierarchy(nodes=(), levels=levels)

    coarse = _detect(nx, graph, _COARSE_RESOLUTION)
    nodes: list[HierarchyNode] = []
    for i, members in enumerate(coarse):
        parent_cid = f"L0-{i}"
        nodes.append(
            HierarchyNode(
                level=0,
                community_id=parent_cid,
                member_ids=tuple(sorted(members)),
                parent_id=None,
                size=len(members),
            )
        )
        if levels < 2:
            continue
        sub = graph.subgraph(members)  # type: ignore[attr-defined]
        fine = _detect(nx, sub, _FINE_RESOLUTION)
        if len(fine) < 2:
            # cannot split further -> keep the level-0 node as a leaf (graceful).
            continue
        for j, submembers in enumerate(fine):
            nodes.append(
                HierarchyNode(
                    level=1,
                    community_id=f"L1-{i}-{j}",
                    member_ids=tuple(sorted(submembers)),
                    parent_id=parent_cid,
                    size=len(submembers),
                )
            )

    hierarchy = CommunityHierarchy(nodes=tuple(nodes), levels=levels)
    _log.info(
        "community_hierarchy.build",
        n_nodes=len(nodes),
        level0=len(hierarchy.at_level(0)),
        level1=len(hierarchy.at_level(1)),
        levels=levels,
    )
    return hierarchy
