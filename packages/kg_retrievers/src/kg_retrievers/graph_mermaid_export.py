"""Mermaid graph-diagram export for docs / markdown embedding (§22.6).

Pure-python serializer (чистый python, только stdlib): render a list of node dicts and
edge dicts as a `Mermaid <https://mermaid.js.org>`_ ``graph`` flowchart that can be
pasted straight into a Markdown (маркдаун) fenced block. No graph/store access, no LLM,
no clock — the input dicts are the single source of truth, and every render is
deterministic for a given input, so the output is hand-checkable.

Mermaid имеет строгий синтаксис: node ids must be bare tokens (no spaces / punctuation),
so :func:`_safe_id` maps every non-alphanumeric character to ``_``; human labels may
contain anything and are therefore *quoted* — a literal ``"`` would close the quoted
label early and break parsing, so :func:`_label` replaces it with the Mermaid entity
``#quot;``.

Entry points:

- :func:`node_decl` — one node declaration ``id["label"]``;
- :func:`edge_decl` — one edge ``s -->|TYPE| t`` (or ``s --> t`` when untyped);
- :func:`to_mermaid` — assemble a :class:`MermaidDiagram` (header + body lines + text);
- :func:`fenced` — wrap a diagram's text in a ```` ```mermaid ```` code block.

Kuzu note: custom node props (name, type, …) are *not* queryable columns — a caller
reading nodes from the store must ``RETURN`` base columns and hydrate the rest via
``get_node`` before handing plain dicts to this module.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Any run of characters that is *not* an ASCII letter or digit is collapsed to a single
# ``_`` so the result is a valid bare Mermaid node id (валидный токен).
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")

# A literal double-quote closes a quoted Mermaid label early; swap it for the entity
# Mermaid renders as ``"`` без поломки синтаксиса.
_QUOT_ENTITY = "#quot;"


def _safe_id(raw: Any) -> str:
    """Map ``raw`` to a Mermaid-safe bare id: non-alphanumerics → ``_`` (§22.6).

    ``'m-1' → 'm_1'``, ``'s' → 's'``. Leading/trailing underscores from surrounding
    punctuation are trimmed so ``'(a)' → 'a'``; a value that is entirely punctuation
    (or empty) falls back to ``'_'`` so the id is never blank.
    """
    token = _NON_ALNUM.sub("_", str(raw)).strip("_")
    return token or "_"


def _label(node: Mapping[str, Any]) -> str:
    """Pick a display label for ``node`` and make it quote-safe (§22.6).

    Prefers ``name``; falls back to ``type``; then to the node's ``id``; finally to an
    empty string. Any ``"`` in the chosen text is replaced with :data:`_QUOT_ENTITY`
    so the quoted label in :func:`node_decl` can never be broken.
    """
    raw = node.get("name") or node.get("type") or node.get("id") or ""
    return str(raw).replace('"', _QUOT_ENTITY)


def node_decl(node: Mapping[str, Any]) -> str:
    """Render one Mermaid node declaration ``id["label"]`` (§22.6).

    The id is :func:`_safe_id` of ``node['id']``; the label is :func:`_label` (name →
    type → id), quoted. E.g. ``{'id': 'm-1', 'name': 'Al 6061'} → 'm_1["Al 6061"]'``.
    """
    return f'{_safe_id(node.get("id"))}["{_label(node)}"]'


def edge_decl(edge: Mapping[str, Any]) -> str:
    """Render one Mermaid edge from ``edge`` (§22.6).

    ``source``/``target`` ids are sanitized with :func:`_safe_id`. A non-empty ``type``
    becomes a pipe label — ``'s -->|HAS| t'`` — while a missing/blank type yields a bare
    arrow ``'s --> t'`` (no pipes). Any ``"`` in the type is made quote-safe.
    """
    src = _safe_id(edge.get("source"))
    tgt = _safe_id(edge.get("target"))
    rel = edge.get("type")
    if rel is None or str(rel) == "":
        return f"{src} --> {tgt}"
    label = str(rel).replace('"', _QUOT_ENTITY)
    return f"{src} -->|{label}| {tgt}"


@dataclass(frozen=True)
class MermaidDiagram:
    """A rendered Mermaid flowchart (§22.6).

    ``direction`` is the flow direction (``'LR'``, ``'TB'``, …); ``lines`` is the body —
    one string per node then per edge, *excluding* the ``graph <dir>`` header; ``text``
    is the full diagram (header + body joined by newlines) ready to embed.
    """

    direction: str
    lines: tuple[str, ...]
    text: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (§22.6) — ``lines`` as a list for JSON-friendliness."""
        return {"direction": self.direction, "lines": list(self.lines), "text": self.text}


def to_mermaid(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    direction: str = "LR",
) -> MermaidDiagram:
    """Serialize ``nodes`` + ``edges`` into a :class:`MermaidDiagram` (§22.6).

    The header is ``f'graph {direction}'`` (so ``direction='TB'`` → first line
    ``'graph TB'``). Body ``lines`` are the node declarations (in input order) followed
    by the edge declarations, so ``len(lines) == len(nodes) + len(edges)``. ``text`` is
    the header joined with the body by ``\\n``; with no nodes/edges ``text`` is exactly
    the header (``'graph LR'`` by default) with no trailing newline.
    """
    header = f"graph {direction}"
    lines = tuple(node_decl(n) for n in nodes) + tuple(edge_decl(e) for e in edges)
    text = header if not lines else header + "\n" + "\n".join(lines)
    return MermaidDiagram(direction=direction, lines=lines, text=text)


def fenced(diagram: MermaidDiagram) -> str:
    """Wrap ``diagram.text`` in a ```` ```mermaid ```` fenced block (§22.6).

    Result starts with ``'```mermaid'`` and ends with ``'```'`` so it embeds directly in
    a Markdown document as a rendered diagram.
    """
    return f"```mermaid\n{diagram.text}\n```"
