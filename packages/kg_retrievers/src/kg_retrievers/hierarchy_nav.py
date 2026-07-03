"""Pure-python navigation over a community hierarchy (§11.14 навигация по иерархии).

Companion to :mod:`kg_retrievers.community_hierarchy`, which *builds* a nested
community structure from the entity graph. This module never touches the store,
networkx or Kuzu — it is a dependency-free (чистый python) navigation layer over
an already-materialised **hierarchy dict of levels**: a mapping ``level -> nodes``
where each node is a small dict describing one community and its parent.

A hierarchy dict of levels looks like::

    {
        0: [{"id": "L0-0", "parent": None, "members": ["a", "b", "c"]}],
        1: [{"id": "L1-0-0", "parent": "L0-0", "members": ["a", "b"]},
            {"id": "L1-0-1", "parent": "L0-0", "members": ["c"]}],
    }

Node dicts accept the same aliases that :meth:`community_hierarchy.HierarchyNode.
as_dict` emits, so a :class:`~kg_retrievers.community_hierarchy.CommunityHierarchy`
grouped by ``level`` drops straight in: ``id``/``community_id`` for the id,
``parent``/``parent_id`` for the parent link, ``members``/``member_ids`` for the
member entities (члены сообщества).

The three navigation primitives mirror the semantics of the builder's own
lookups: :func:`children_of` (дети), :func:`parent_of` (родитель) and
:func:`path_to_root` (путь до корня). All are read-only and cycle-safe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Accepted node-dict key aliases (community_hierarchy.as_dict compatibility).
_ID_KEYS = ("id", "community_id")
_PARENT_KEYS = ("parent", "parent_id")
_MEMBER_KEYS = ("members", "member_ids")


@dataclass(frozen=True)
class NavNode:
    """One community in a navigable hierarchy (§11.14 узел иерархии).

    Attributes:
        node_id: id of this community (кластер).
        level: 0-based depth; 0 is a coarse root, larger is finer/deeper.
        parent_id: id of the enclosing community, or None for a root (корень).
        member_ids: entity ids that belong to this community (члены).
    """

    node_id: str
    level: int
    parent_id: str | None
    member_ids: tuple[str, ...]

    def as_dict(self) -> dict:
        """Serialise to a plain JSON-ready dict (copies ``member_ids``)."""
        return {
            "node_id": self.node_id,
            "level": self.level,
            "parent_id": self.parent_id,
            "member_ids": list(self.member_ids),
        }


@dataclass(frozen=True)
class HierarchyView:
    """Immutable, navigable view over a hierarchy dict of levels (§11.14).

    Built via :meth:`from_levels`; holds a flat, level-ordered tuple of
    :class:`NavNode`. Accepted anywhere a raw levels dict is (see module docs),
    so callers may pre-normalise once and reuse the view.
    """

    nodes: tuple[NavNode, ...] = ()

    @classmethod
    def from_levels(cls, hierarchy: HierarchyLike) -> HierarchyView:
        """Normalise a levels dict (or another view) into a flat view."""
        return cls(nodes=tuple(_iter_nodes(hierarchy)))

    def as_dict(self) -> dict:
        """Serialise the whole view: counts, roots, and every node."""
        return {
            "n_nodes": len(self.nodes),
            "n_levels": len({n.level for n in self.nodes}),
            "roots": [n.node_id for n in self.nodes if n.parent_id is None],
            "nodes": [n.as_dict() for n in self.nodes],
        }


# A hierarchy is either a raw dict of levels or an already-built view.
HierarchyLike = Mapping[int, Sequence[Mapping[str, object]]] | HierarchyView


def _first(raw: Mapping[str, object], keys: Sequence[str], default: object) -> object:
    """Return ``raw[k]`` for the first alias ``k`` present, else ``default``."""
    for key in keys:
        if key in raw:
            return raw[key]
    return default


def _coerce(level: int, raw: Mapping[str, object]) -> NavNode:
    """Build a :class:`NavNode` from a raw node dict at ``level``."""
    parent = _first(raw, _PARENT_KEYS, None)
    members = _first(raw, _MEMBER_KEYS, ())
    if not isinstance(members, (list, tuple)):
        members = ()
    return NavNode(
        node_id=str(_first(raw, _ID_KEYS, "")),
        level=int(level),
        parent_id=None if parent is None else str(parent),
        member_ids=tuple(str(m) for m in members),
    )


def _iter_nodes(hierarchy: HierarchyLike):  # type: ignore[no-untyped-def]
    """Yield every :class:`NavNode`, levels ascending, order preserved within."""
    if isinstance(hierarchy, HierarchyView):
        yield from hierarchy.nodes
        return
    for level in sorted(hierarchy):
        for raw in hierarchy[level]:
            yield _coerce(level, raw)


def _index(hierarchy: HierarchyLike) -> dict[str, NavNode]:
    """Map ``node_id -> NavNode`` (last wins on duplicate ids)."""
    return {n.node_id: n for n in _iter_nodes(hierarchy)}


def children_of(hierarchy: HierarchyLike, parent_id: str) -> list[str]:
    """Ids of communities nested directly under ``parent_id`` (дети).

    Returns them in level-then-insertion order. An unknown ``parent_id`` — or a
    leaf with no sub-communities — yields ``[]``.
    """
    return [n.node_id for n in _iter_nodes(hierarchy) if n.parent_id == parent_id]


def parent_of(hierarchy: HierarchyLike, child_id: str) -> str | None:
    """Id of the community enclosing ``child_id`` (родитель), or None.

    None means either ``child_id`` is a root or it is not in the hierarchy.
    """
    node = _index(hierarchy).get(child_id)
    return node.parent_id if node is not None else None


def path_to_root(hierarchy: HierarchyLike, node_id: str) -> list[str]:
    """Ids from ``node_id`` up to its root, inclusive (путь до корня).

    ``[node_id, parent, ..., root]``. A root maps to ``[node_id]``. An unknown
    ``node_id`` yields ``[]``. Cycle-safe: a broken parent chain stops instead of
    looping forever.
    """
    index = _index(hierarchy)
    if node_id not in index:
        return []
    path: list[str] = []
    seen: set[str] = set()
    current: str | None = node_id
    while current is not None and current in index and current not in seen:
        path.append(current)
        seen.add(current)
        current = index[current].parent_id
    return path
