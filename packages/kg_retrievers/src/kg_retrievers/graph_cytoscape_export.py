"""Cytoscape.js *elements JSON* export for graph nodes/edges (§22.6).

Pure-python (stdlib :mod:`json` only) serializer that converts plain node / edge dicts
into the Cytoscape.js ``elements`` JSON shape — the format the Cytoscape.js UI mode
(§17) renders and round-trips::

    {"elements": {"nodes": [{"data": {"id": ..., "label": ...}}],
                  "edges": [{"data": {"id": ..., "source": ..., "target": ...}}]}}

No graph/store access, no LLM, no clock: the caller-supplied dicts are the single source
of truth, so the export is deterministic for a given input. Каждый узел (node) и ребро
(edge) кладётся в ``data``: базовые поля (id / label / source / target) плюс любые
пользовательские свойства (properties) вложены под ``data`` — так их читает UI-слой.

Entry points:

- :func:`node_element` — one node dict → ``{"data": {...}}`` element;
- :func:`edge_element` — one edge dict → ``{"data": {...}}`` element;
- :func:`to_cytoscape` — bundle nodes + edges into a :class:`CytoscapeGraph`;
- :func:`to_json` — serialize nodes + edges straight to a JSON string.

Kuzu note: custom node props are *not* queryable columns — a caller reading a node from
the store must ``RETURN`` base columns and hydrate the rest via ``get_node`` before
handing the assembled dict here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Node keys consumed to build the ``data.id`` / ``data.label`` fields; every *other*
# key on the node dict is copied verbatim into ``data`` as a custom property.
_NODE_ID_KEYS = ("id",)
_NODE_LABEL_KEYS = ("name",)

# Edge keys consumed to build ``data.id`` / source / target / label; the rest are copied
# into ``data`` as custom edge properties.
_EDGE_SOURCE_KEYS = ("source", "src", "s")
_EDGE_TARGET_KEYS = ("target", "dst", "t")
_EDGE_TYPE_KEYS = ("type", "rel", "label")


def _first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """Return the first present value among ``keys`` in ``mapping`` (else ``None``)."""
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def node_element(node: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one ``node`` dict into a Cytoscape.js element (§22.6).

    ``data.id`` comes from the node's ``id``; ``data.label`` from its ``name`` and falls
    back to the id when ``name`` is missing/empty. Any remaining keys (кроме id/name) are
    nested under ``data`` verbatim, e.g. ``node_element({"id": "m1", "hardness": 5})``
    yields ``data["hardness"] == 5``.
    """
    node_id = _first(node, _NODE_ID_KEYS)
    id_str = "" if node_id is None else str(node_id)
    label = _first(node, _NODE_LABEL_KEYS)
    label_str = str(label) if label not in (None, "") else id_str

    data: dict[str, Any] = {"id": id_str, "label": label_str}
    _consumed = set(_NODE_ID_KEYS) | set(_NODE_LABEL_KEYS)
    for key, value in node.items():
        if key not in _consumed:
            data[key] = value
    return {"data": data}


def edge_element(edge: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one ``edge`` dict into a Cytoscape.js element (§22.6).

    ``data.source`` / ``data.target`` come from the edge's endpoints; ``data.label`` from
    its relationship type; ``data.id`` is a stable ``"<source>-<type>-<target>"`` string.
    Extra keys (кроме endpoints/type) are nested under ``data`` verbatim.
    """
    source = _first(edge, _EDGE_SOURCE_KEYS)
    target = _first(edge, _EDGE_TARGET_KEYS)
    rel = _first(edge, _EDGE_TYPE_KEYS)
    source_str = "" if source is None else str(source)
    target_str = "" if target is None else str(target)
    rel_str = "" if rel is None else str(rel)

    edge_id = _first(edge, ("id",))
    id_str = str(edge_id) if edge_id is not None else f"{source_str}-{rel_str}-{target_str}"

    data: dict[str, Any] = {
        "id": id_str,
        "source": source_str,
        "target": target_str,
        "label": rel_str,
    }
    _consumed = {"id"} | set(_EDGE_SOURCE_KEYS) | set(_EDGE_TARGET_KEYS) | set(_EDGE_TYPE_KEYS)
    for key, value in edge.items():
        if key not in _consumed:
            data[key] = value
    return {"data": data}


@dataclass(frozen=True)
class CytoscapeGraph:
    """A Cytoscape.js graph: converted node + edge elements (§22.6).

    ``nodes`` / ``edges`` hold the *converted* elements (each a ``{"data": {...}}`` dict);
    :meth:`as_dict` wraps them in the nested ``{"elements": {...}}`` envelope the UI reads.
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the nested Cytoscape.js ``{"elements": {"nodes": ..., "edges": ...}}``."""
        return {
            "elements": {
                "nodes": [dict(n) for n in self.nodes],
                "edges": [dict(e) for e in self.edges],
            }
        }


def to_cytoscape(
    nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> CytoscapeGraph:
    """Bundle ``nodes`` + ``edges`` into a :class:`CytoscapeGraph` (§22.6)."""
    return CytoscapeGraph(
        nodes=tuple(node_element(n) for n in nodes),
        edges=tuple(edge_element(e) for e in edges),
    )


def to_json(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    indent: int | None = None,
) -> str:
    """Serialize ``nodes`` + ``edges`` to a Cytoscape.js elements JSON string (§22.6).

    ``ensure_ascii=False`` keeps RU text (кириллица) verbatim; ``indent`` is forwarded to
    :func:`json.dumps` (``None`` → compact). ``json.loads(to_json(ns, es))`` equals
    ``to_cytoscape(ns, es).as_dict()`` for JSON-native values, so the export round-trips.
    """
    return json.dumps(to_cytoscape(nodes, edges).as_dict(), indent=indent, ensure_ascii=False)
