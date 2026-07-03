"""Apache TinkerPop *GraphSON v3* line-delimited export for graph nodes/edges (§22.6).

Pure-python (stdlib :mod:`json` only) serializer that converts plain node / edge dicts
into TinkerPop's GraphSON v3 *line-delimited* form — one vertex object per line, each a
standalone JSON document::

    {"id": ..., "label": ..., "outE": {rel: [{"id": edgeId, "inV": target}]},
     "properties": {k: [{"value": v}]}}

This is the graph-import format the repo lacked: it already ships GraphML / GEXF / DOT /
Cytoscape / JSON-LD / N-Triples, but no GraphSON. No graph/store access, no LLM, no clock:
the caller-supplied dicts are the single source of truth, so the export is deterministic
for a given input. Каждая вершина (vertex) занимает ровно одну строку; исходящие рёбра
(out-edges) группируются под ``outE`` по типу связи (rel type), а пользовательские
свойства (properties) — под ``properties`` по ключу.

Entry points:

- :func:`vertex_object` — one node dict + its out-edges → a :class:`GraphsonVertex`;
- :func:`to_graphson` — bundle nodes + edges into the newline-terminated GraphSON string.

Kuzu note: custom node props are *not* queryable columns — a caller reading a node from
the store must ``RETURN`` base columns and hydrate the rest via ``get_node`` before
handing the assembled dict here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Node keys consumed to build ``id`` / ``label``; every *other* key becomes a property.
_NODE_ID_KEYS = ("id",)
_NODE_LABEL_KEYS = ("label",)
_RESERVED_NODE_KEYS = frozenset(_NODE_ID_KEYS) | frozenset(_NODE_LABEL_KEYS)

# Edge keys consumed to derive source / target / rel-type from an edge dict.
_EDGE_SOURCE_KEYS = ("source", "src", "s")
_EDGE_TARGET_KEYS = ("target", "dst", "t")
_EDGE_TYPE_KEYS = ("type", "rel", "label")


def _first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """Return the first present value among ``keys`` in ``mapping`` (else ``None``)."""
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


@dataclass(frozen=True)
class GraphsonVertex:
    """A single GraphSON v3 vertex: id, label, out-edges and properties (§22.6).

    ``out_edges`` holds ``(rel_type, target_id)`` pairs — one per outgoing edge, so two
    edges of the same rel type appear as two pairs and land in one ``outE`` list.
    ``properties`` holds ``(key, value)`` pairs. :meth:`as_dict` inflates both into the
    nested GraphSON v3 shape the TinkerPop importer reads.
    """

    id: str
    label: str
    out_edges: tuple[tuple[str, str], ...]
    properties: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the GraphSON v3 vertex object (§22.6).

        Edge ids are synthesized deterministically as ``"<id>-<rel>-<target>"``; multiple
        edges of the same rel type accumulate in a single list under ``outE[rel]``, and
        each property value is wrapped as ``[{"value": v}]`` under ``properties[key]``.
        """
        out_e: dict[str, list[dict[str, str]]] = {}
        for rel, target in self.out_edges:
            edge_id = f"{self.id}-{rel}-{target}"
            out_e.setdefault(rel, []).append({"id": edge_id, "inV": target})

        props: dict[str, list[dict[str, str]]] = {}
        for key, value in self.properties:
            props.setdefault(key, []).append({"value": value})

        return {"id": self.id, "label": self.label, "outE": out_e, "properties": props}


def vertex_object(
    node: Mapping[str, Any], edges_by_source: Mapping[str, Sequence[Mapping[str, Any]]]
) -> GraphsonVertex:
    """Convert one ``node`` dict + its out-edges into a :class:`GraphsonVertex` (§22.6).

    ``id`` comes from the node's ``id`` and ``label`` from its ``label`` (empty string
    when absent). Any remaining keys (кроме id/label) become string-valued properties.
    ``edges_by_source`` maps a source id to that vertex's outgoing edge dicts; each edge's
    rel type / target are read via the usual key aliases and stored as an ``out_edges``
    pair. Edges are kept in input order, so same-rel edges preserve their given sequence.
    """
    node_id = _first(node, _NODE_ID_KEYS)
    id_str = "" if node_id is None else str(node_id)
    label = _first(node, _NODE_LABEL_KEYS)
    label_str = "" if label is None else str(label)

    properties = tuple(
        (key, str(value)) for key, value in node.items() if key not in _RESERVED_NODE_KEYS
    )

    out_edges: list[tuple[str, str]] = []
    for edge in edges_by_source.get(id_str, ()):
        rel = _first(edge, _EDGE_TYPE_KEYS)
        target = _first(edge, _EDGE_TARGET_KEYS)
        rel_str = "" if rel is None else str(rel)
        target_str = "" if target is None else str(target)
        out_edges.append((rel_str, target_str))

    return GraphsonVertex(
        id=id_str,
        label=label_str,
        out_edges=tuple(out_edges),
        properties=properties,
    )


def to_graphson(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> str:
    """Serialize ``nodes`` + ``edges`` to a line-delimited GraphSON v3 string (§22.6).

    Edges are first grouped by their source id, then every node is emitted as one
    newline-terminated JSON line (``ensure_ascii=False`` keeps кириллица verbatim). The
    result has exactly ``len(nodes)`` lines; an empty ``nodes`` sequence yields ``''``.
    """
    edges_by_source: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        source = _first(edge, _EDGE_SOURCE_KEYS)
        source_str = "" if source is None else str(source)
        edges_by_source.setdefault(source_str, []).append(edge)

    lines = []
    for node in nodes:
        vertex = vertex_object(node, edges_by_source)
        lines.append(json.dumps(vertex.as_dict(), ensure_ascii=False))
    return "".join(f"{line}\n" for line in lines)
