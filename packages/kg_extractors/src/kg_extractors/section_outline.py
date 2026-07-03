"""Document outline / table-of-contents tree from chunks (§5.7).

Chunks carry a ``section_path`` — the ordered list of section headings that
locate the chunk inside its document (``['Results', 'Mechanism']``). Folding a
whole batch of those paths gives back the document's *outline*: a nested forest
of :class:`OutlineNode`, one branch per distinct heading, with each node knowing
how many chunks land *exactly* on it and how many land anywhere in its subtree.
Curators use the outline to see a document's shape at a glance — which sections
are dense, which are thin, and whether the heading hierarchy is well formed —
before the chunks are handed to the extractors.

Shape of the tree:

* the result is a *forest* — a tuple of root nodes, one per distinct top heading,
  in first-seen order (синтетический лес корней);
* each node's ``path`` is the full heading chain from a root down to it, so the
  ``Mechanism`` under ``Results`` has ``path == ('Results', 'Mechanism')``;
* ``depth`` is the 0-based level (roots are depth ``0``);
* ``chunk_count`` counts only the chunks whose ``section_path`` ends *exactly* at
  this node — chunks deeper in the subtree are **not** counted here (точный узел);
* intermediate headings that no chunk ends on still get a node with
  ``chunk_count == 0`` — e.g. a lone path ``['A', 'B', 'C']`` builds the whole
  ``A → B → C`` chain (промежуточные узлы).

:func:`total_chunks` rolls a node and all its descendants up into one number, so
``total_chunks(root)`` is every chunk anywhere under that root. Insertion order is
preserved everywhere, so the forest is stable and hand-checkable. Pure Python —
stdlib only, no LLM, no I/O.

Public API:

- :class:`OutlineNode` — frozen outline node with recursive :meth:`OutlineNode.as_dict`;
- :func:`build_outline` — fold ``section_path`` lists into a forest of roots;
- :func:`total_chunks` — sum a node and all descendants.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutlineNode:
    """One heading in the document outline tree (§5.7).

    Fields
    ------
    title
        The heading text at this level — the last element of ``path`` (заголовок).
    depth
        0-based level in the forest; roots are ``0`` (глубина).
    path
        Full heading chain from a root down to this node, as a tuple
        (``('Results', 'Mechanism')``); ``path[-1] == title`` (полный путь).
    chunk_count
        Number of chunks whose ``section_path`` ends *exactly* at this node;
        chunks deeper in the subtree are counted on their own node, not here
        (чанков ровно на этом узле).
    children
        Child nodes in first-seen order (дочерние узлы).
    """

    title: str
    depth: int
    path: tuple[str, ...]
    chunk_count: int
    children: tuple[OutlineNode, ...]

    def as_dict(self) -> dict[str, object]:
        """Full structured view, recursing into ``children`` (JSON-friendly)."""
        return {
            "title": self.title,
            "depth": self.depth,
            "path": list(self.path),
            "chunk_count": self.chunk_count,
            "children": [child.as_dict() for child in self.children],
        }


class _Builder:
    """Mutable scratch node used while folding paths (не публичный API)."""

    __slots__ = ("children", "count", "depth", "path", "title")

    def __init__(self, title: str, depth: int, path: tuple[str, ...]) -> None:
        self.title = title
        self.depth = depth
        self.path = path
        self.count = 0
        self.children: dict[str, _Builder] = {}

    def freeze(self) -> OutlineNode:
        """Recursively freeze into an immutable :class:`OutlineNode`."""
        return OutlineNode(
            title=self.title,
            depth=self.depth,
            path=self.path,
            chunk_count=self.count,
            children=tuple(child.freeze() for child in self.children.values()),
        )


def build_outline(chunks: list[dict]) -> tuple[OutlineNode, ...]:
    """Fold chunk ``section_path`` lists into a forest of outline roots (§5.7).

    Walks ``chunks`` once, in input order. Each chunk's ``section_path`` (a list
    of heading strings) is turned into a chain of nodes; nodes are created lazily
    the first time a prefix is seen, preserving first-seen sibling order. The
    chunk's ``chunk_count`` is credited to the *last* node on its path, so
    intermediate headings that no chunk ends on keep ``chunk_count == 0`` while
    still existing as nodes. Chunks with an empty or missing ``section_path`` are
    skipped. An empty input yields an empty tuple.
    """
    roots: dict[str, _Builder] = {}
    for chunk in chunks:
        section_path = chunk.get("section_path") or []
        if not section_path:
            continue
        level = roots
        node: _Builder | None = None
        prefix: tuple[str, ...] = ()
        for depth, title in enumerate(section_path):
            prefix = (*prefix, title)
            node = level.get(title)
            if node is None:
                node = _Builder(title=title, depth=depth, path=prefix)
                level[title] = node
            level = node.children
        if node is not None:
            node.count += 1
    return tuple(root.freeze() for root in roots.values())


def total_chunks(node: OutlineNode) -> int:
    """Sum ``chunk_count`` over ``node`` and every descendant (§5.7).

    ``total_chunks(root)`` is therefore every chunk that lands anywhere in that
    root's subtree, however deep.
    """
    return node.chunk_count + sum(total_chunks(child) for child in node.children)
