"""GraphML 1.0 graph serialization (§22.6).

Turns *canonical* node dicts (``{id, type|label, name, properties}``) and edge dicts
(``{source, target, type}``) into a GraphML 1.0 XML document — the де-факто interchange
format read by Gephi, Cytoscape, networkx and friends. Pure python: the *only* stdlib
dependency is :func:`xml.sax.saxutils.escape`, so a node ``name`` carrying ``&``/``<``/``>``
serializes to well-formed XML (``&amp;`` …). No graph/store access, no LLM, no clock —
the input dicts are the single source of truth and every render is deterministic.

Модель (model): GraphML declares each attribute *once* as a ``<key>`` (with a ``for``
scope — ``node`` or ``edge`` — an ``attr.name`` and an ``attr.type``), then references it
per element via ``<data key="…">``. :func:`collect_keys` walks the property dicts in
*first-seen* order (deterministic across repeat calls) and infers the GraphML type from
the python value: ``bool -> boolean``, ``int -> long``, ``float -> double``, else
``string`` (``bool`` is checked before ``int`` since ``bool`` subclasses ``int``).

Entry points:

- :class:`GraphMLKey` — one ``<key>`` declaration (id / for / attr.name / attr.type);
- :class:`GraphMLDoc` — frozen result: the ordered ``keys`` tuple plus the ``xml`` string;
- :func:`collect_keys` — union of property names over nodes then edges, first-seen order;
- :func:`nodes_edges_to_graphml` — build a :class:`GraphMLDoc` (``directed`` toggles
  ``edgedefault``);
- :func:`graphml_document` — convenience wrapper returning just the XML string.

Kuzu note: custom node props are *not* queryable columns — a caller reading nodes from the
store must ``RETURN`` base columns and hydrate the rest via ``get_node`` before handing the
canonical dicts here (tests build a temp store / in-memory dicts, never query custom props).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

# GraphML attr.type strings (§22.6) — stable so renders stay hand-checkable.
_TYPE_BOOLEAN = "boolean"
_TYPE_LONG = "long"
_TYPE_DOUBLE = "double"
_TYPE_STRING = "string"

# GraphML <key> scopes.
_FOR_NODE = "node"
_FOR_EDGE = "edge"

# GraphML 1.0 root element with the canonical graphml.graphdrawing.org namespace.
_GRAPHML_OPEN = (
    '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
    'http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">'
)


def _infer_type(value: Any) -> str:
    """Infer the GraphML ``attr.type`` for a python *value* (тип из значения).

    ``bool`` is tested before ``int`` because ``bool`` subclasses ``int``.
    """
    if isinstance(value, bool):
        return _TYPE_BOOLEAN
    if isinstance(value, int):
        return _TYPE_LONG
    if isinstance(value, float):
        return _TYPE_DOUBLE
    return _TYPE_STRING


@dataclass(frozen=True)
class GraphMLKey:
    """One GraphML ``<key>`` declaration (объявление атрибута).

    ``id`` — the ``key`` id referenced by ``<data key=…>``; ``for_`` — scope
    (``node``/``edge``); ``attr_name`` — the original property name; ``attr_type`` —
    the inferred GraphML type (``boolean``/``long``/``double``/``string``).
    """

    id: str
    for_: str
    attr_name: str
    attr_type: str

    def as_dict(self) -> dict[str, str]:
        """Return a plain-dict view (обычный словарь) for JSON / inspection."""
        return {
            "id": self.id,
            "for": self.for_,
            "attr_name": self.attr_name,
            "attr_type": self.attr_type,
        }

    def to_xml(self) -> str:
        """Render this key as a self-closing ``<key/>`` element."""
        return (
            f'<key id="{escape(self.id)}" for="{escape(self.for_)}" '
            f'attr.name="{escape(self.attr_name)}" attr.type="{self.attr_type}"/>'
        )


@dataclass(frozen=True)
class GraphMLDoc:
    """Frozen GraphML result (результат): the ordered ``keys`` and the ``xml`` string."""

    keys: tuple[GraphMLKey, ...]
    xml: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (обычный словарь) for JSON / inspection."""
        return {"keys": [k.as_dict() for k in self.keys], "xml": self.xml}


def _properties(item: Mapping[str, Any]) -> Mapping[str, Any]:
    """Extract the ``properties`` mapping from a canonical dict (may be absent)."""
    props = item.get("properties")
    if isinstance(props, Mapping):
        return props
    return {}


def collect_keys(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> list[GraphMLKey]:
    """Union of property names over *nodes* then *edges*, first-seen order (детерминизм).

    Node properties get ``for="node"`` keys prefixed ``d`` (``d0``, ``d1``, …); edge
    properties get ``for="edge"`` keys prefixed ``e`` (``e0``, ``e1``, …). The first
    value seen for a name fixes its inferred type. Calling twice with the same input
    yields an equal list (idempotent).
    """
    keys: list[GraphMLKey] = []

    seen_node: dict[str, GraphMLKey] = {}
    for node in nodes:
        for name, value in _properties(node).items():
            if name in seen_node:
                continue
            key = GraphMLKey(
                id=f"d{len(seen_node)}",
                for_=_FOR_NODE,
                attr_name=name,
                attr_type=_infer_type(value),
            )
            seen_node[name] = key
            keys.append(key)

    seen_edge: dict[str, GraphMLKey] = {}
    for edge in edges:
        for name, value in _properties(edge).items():
            if name in seen_edge:
                continue
            key = GraphMLKey(
                id=f"e{len(seen_edge)}",
                for_=_FOR_EDGE,
                attr_name=name,
                attr_type=_infer_type(value),
            )
            seen_edge[name] = key
            keys.append(key)

    return keys


def _data_value(value: Any) -> str:
    """Render a property *value* as escaped GraphML ``<data>`` text (booleans lower-case)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return escape(str(value))


def _node_xml(node: Mapping[str, Any], key_by_name: Mapping[str, GraphMLKey]) -> str:
    """Render one ``<node>`` element with its ``<data>`` children."""
    node_id = escape(str(node.get("id", "")))
    parts = [f'<node id="{node_id}">']
    for name, value in _properties(node).items():
        key = key_by_name.get(name)
        if key is None:
            continue
        parts.append(f'<data key="{escape(key.id)}">{_data_value(value)}</data>')
    parts.append("</node>")
    return "".join(parts)


def _edge_xml(edge: Mapping[str, Any], key_by_name: Mapping[str, GraphMLKey]) -> str:
    """Render one ``<edge>`` element with its ``<data>`` children."""
    source = escape(str(edge.get("source", "")))
    target = escape(str(edge.get("target", "")))
    parts = [f'<edge source="{source}" target="{target}">']
    for name, value in _properties(edge).items():
        key = key_by_name.get(name)
        if key is None:
            continue
        parts.append(f'<data key="{escape(key.id)}">{_data_value(value)}</data>')
    parts.append("</edge>")
    return "".join(parts)


def nodes_edges_to_graphml(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    directed: bool = True,
) -> GraphMLDoc:
    """Serialize canonical *nodes* / *edges* into a :class:`GraphMLDoc` (§22.6).

    ``directed`` toggles ``edgedefault`` between ``directed`` and ``undirected``. Keys are
    declared once (via :func:`collect_keys`) before the ``<graph>`` body, per the spec.
    """
    keys = collect_keys(nodes, edges)
    node_key_by_name = {k.attr_name: k for k in keys if k.for_ == _FOR_NODE}
    edge_key_by_name = {k.attr_name: k for k in keys if k.for_ == _FOR_EDGE}

    edgedefault = "directed" if directed else "undirected"
    parts: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', _GRAPHML_OPEN]
    parts.extend(k.to_xml() for k in keys)
    parts.append(f'<graph edgedefault="{edgedefault}">')
    parts.extend(_node_xml(n, node_key_by_name) for n in nodes)
    parts.extend(_edge_xml(e, edge_key_by_name) for e in edges)
    parts.append("</graph>")
    parts.append("</graphml>")

    return GraphMLDoc(keys=tuple(keys), xml="".join(parts))


def graphml_document(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> str:
    """Convenience wrapper: return just the GraphML XML string (directed graph)."""
    return nodes_edges_to_graphml(nodes, edges).xml
