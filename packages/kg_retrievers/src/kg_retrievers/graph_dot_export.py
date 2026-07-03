"""§22.6 — Graphviz DOT export for knowledge-graph subgraphs.

Чистый сериализатор (pure serializer): turns plain node/edge dicts into a
Graphviz ``digraph`` string, ready to pipe into ``dot -Tsvg`` or paste into any
DOT viewer. No graph store, no I/O — only dicts in, text out — so it stays
trivially testable and free of the Kuzu column caveat (custom node props are not
queryable columns; here every field is just read off the dict the caller hands
us).

Each node becomes one ``"id" [label=... , style=filled, fillcolor=...]`` line;
its label is drawn from ``name`` (falling back to ``type`` then ``id``), and its
fill colour is chosen per node ``type`` from :data:`TYPE_FILL_COLORS`. Each edge
becomes one ``"src" -> "tgt" [label="REL"]`` line, labelled by its relation
``type``. Both quote every identifier and escape embedded quotes / newlines via
:func:`_quote`, so arbitrary names cannot break the DOT syntax.

:func:`to_dot` assembles the body and returns a frozen :class:`DotGraph`
carrying the assembled ``body`` plus node / edge counts; :func:`render` wraps
that body in the outer ``digraph <name> { ... }`` with the graph ``rankdir``
(``LR`` by default, override to ``TB`` for a top-down layout).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# -- per-type fill colours (§22.6) -----------------------------------------
# Каждому типу — свой цвет (a colour per type); unknown types render unfilled.
TYPE_FILL_COLORS: dict[str, str] = {
    "Material": "#cde8d0",
    "Property": "#cdd8e8",
    "Measurement": "#e8e0cd",
    "Document": "#e8cdd8",
    "Chunk": "#e8e8cd",
    "Method": "#d8cde8",
}

_INDENT = "  "


@dataclass(frozen=True)
class DotGraph:
    """§22.6 — assembled DOT body plus its node / edge counts.

    ``body`` holds the indented node/edge lines (no outer braces); :func:`render`
    wraps it. RU: тело графа без внешних скобок.
    """

    name: str
    body: str
    node_count: int
    edge_count: int

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (RU: словарь) for logging / JSON."""
        return {
            "name": self.name,
            "body": self.body,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
        }


def _quote(s: Any) -> str:
    """Escape ``"`` and newlines so ``s`` is a safe DOT quoted-id body.

    RU: экранируем кавычки и переводы строк. Returns the *inner* text (without
    the surrounding quotes) with ``"`` -> ``\\"`` and newlines -> ``\\n``.
    """
    text = str(s)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return text


def _node_label(node: dict[str, Any]) -> str:
    """Pick a node label: ``name`` -> ``type`` -> ``id`` (RU: имя/тип/идентификатор)."""
    for key in ("name", "type", "id"):
        val = node.get(key)
        if val is not None and str(val) != "":
            return str(val)
    return ""


def node_line(node: dict[str, Any]) -> str:
    """Serialize one node dict to a DOT statement line.

    Uses ``id`` as the quoted node id, :func:`_node_label` for the label, and
    :data:`TYPE_FILL_COLORS` for a per-type fill (``style=filled``) when the type
    is known. RU: одна строка узла.
    """
    node_id = _quote(node.get("id", ""))
    label = _quote(_node_label(node))
    attrs = [f'label="{label}"']
    color = TYPE_FILL_COLORS.get(str(node.get("type", "")))
    if color is not None:
        attrs.append("style=filled")
        attrs.append(f'fillcolor="{color}"')
    return f'"{node_id}" [{", ".join(attrs)}];'


def edge_line(edge: dict[str, Any]) -> str:
    """Serialize one edge dict (``source``/``target``/``type``) to a DOT line.

    RU: одна строка ребра. Accepts ``source`` or ``src``, ``target`` or ``tgt``.
    Adds a ``label="REL"`` when a relation ``type`` is present.
    """
    src = _quote(edge.get("source", edge.get("src", "")))
    tgt = _quote(edge.get("target", edge.get("tgt", "")))
    rel = edge.get("type", edge.get("rel"))
    body = f'"{src}" -> "{tgt}"'
    if rel is not None and str(rel) != "":
        return f'{body} [label="{_quote(rel)}"];'
    return f"{body};"


def to_dot(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    name: str = "kg",
    rankdir: str = "LR",
) -> DotGraph:
    """Assemble node/edge dicts into a :class:`DotGraph` body (§22.6).

    RU: собираем тело графа. ``rankdir`` is emitted as a graph attribute in the
    body so :func:`render` reproduces it regardless of wrapper name.
    """
    lines: list[str] = [f"rankdir={_quote(rankdir)};"]
    for node in nodes:
        lines.append(node_line(node))
    for edge in edges:
        lines.append(edge_line(edge))
    body = "\n".join(f"{_INDENT}{line}" for line in lines)
    return DotGraph(
        name=name,
        body=body,
        node_count=len(nodes),
        edge_count=len(edges),
    )


def render(dotgraph: DotGraph) -> str:
    """Wrap a :class:`DotGraph` body into a full ``digraph <name> { ... }``.

    RU: полный текст DOT-диграфа. Ends with a closing ``}`` on its own line.
    """
    return f"digraph {dotgraph.name} {{\n{dotgraph.body}\n}}"
