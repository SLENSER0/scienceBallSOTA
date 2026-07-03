"""§22.6 — JSON-LD graph serializer for knowledge-graph subgraphs.

Чистый сериализатор (pure serializer): turns plain node/edge dicts into a
JSON-LD *graph* document of the shape ``{"@context": ..., "@graph": [...]}``.
Stdlib ``json`` only — no graph store, no I/O — so it stays trivially testable
and free of the Kuzu column caveat (custom node props are not queryable columns;
here every field is simply read off the dict the caller hands us).

This is deliberately *distinct* from the answer-shaped JSON-LD emitted by the
api-gateway: that one describes an answer envelope, whereas this one describes
the graph itself. Each node becomes one JSON-LD object carrying ``@id`` (a
prefixed ``kg:`` IRI), ``@type`` (from the node ``label``), and every remaining
key as a literal property. Edges are *folded into their subject node*: an edge
``s -> t`` of type ``REL`` gives the subject object a key ``REL`` whose value is
a reference ``{"@id": <target-iri>}``. Two edges of the same predicate from one
subject collapse into a JSON-LD list of such references.

:func:`node_object` maps one node dict to its object; :func:`attach_edges`
mutates an ``id -> object`` map in place to fold the edges in;
:func:`to_jsonld` assembles both into a frozen :class:`JsonLdGraph`; and
:func:`to_json` returns the serialized JSON text (round-trips via ``json.loads``
back to :meth:`JsonLdGraph.as_dict`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# -- default JSON-LD context (§22.6) ---------------------------------------
# ``@vocab`` resolves bare predicate/property terms; ``kg`` is the node-id
# prefix. RU: контекст по умолчанию — базовый словарь и префикс идентификаторов.
DEFAULT_CONTEXT: dict[str, Any] = {
    "@vocab": "https://scienceball.example/kg/vocab#",
    "kg": "https://scienceball.example/kg/id/",
}

# Keys consumed structurally rather than emitted as literal properties.
# RU: служебные ключи (id -> @id, label -> @type).
_RESERVED_KEYS: frozenset[str] = frozenset({"id", "label"})


@dataclass(frozen=True)
class JsonLdGraph:
    """§22.6 — a JSON-LD graph document: its ``@context`` and ``@graph`` nodes.

    ``context`` is emitted verbatim under ``@context``; ``graph`` is the ordered
    tuple of node objects emitted under ``@graph``. RU: контекст и узлы графа.
    """

    context: dict[str, Any]
    graph: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-LD document as a plain dict (RU: словарь-документ)."""
        return {"@context": self.context, "@graph": list(self.graph)}


def _iri(node_id: Any) -> str:
    """Build a prefixed ``kg:`` IRI for a node id (RU: префиксный идентификатор)."""
    return f"kg:{node_id}"


def node_object(node: dict[str, Any]) -> dict[str, Any]:
    """Serialize one node dict to a JSON-LD object.

    ``id`` -> ``@id`` (prefixed ``kg:`` IRI), ``label`` -> ``@type``, and every
    other key is copied through as a literal property. RU: один узел -> объект.
    Reserved keys with a ``None`` value are simply skipped.
    """
    obj: dict[str, Any] = {}
    node_id = node.get("id")
    if node_id is not None:
        obj["@id"] = _iri(node_id)
    label = node.get("label")
    if label is not None:
        obj["@type"] = str(label)
    for key, val in node.items():
        if key in _RESERVED_KEYS:
            continue
        obj[key] = val
    return obj


def attach_edges(
    objects_by_id: dict[Any, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    """Fold ``edges`` into their subject objects in place (RU: сворачиваем рёбра).

    ``objects_by_id`` maps raw node ids to their JSON-LD objects. For each edge
    (``source``/``src`` -> ``target``/``tgt`` of ``type``/``rel``), the subject
    object gains a key named after the predicate whose value is a reference
    ``{"@id": <target-iri>}``. A second edge of the same predicate promotes the
    value to a list of references. Edges with a missing endpoint/predicate, or
    an unknown subject, are ignored.
    """
    for edge in edges:
        src = edge.get("source", edge.get("src"))
        tgt = edge.get("target", edge.get("tgt"))
        pred = edge.get("type", edge.get("rel"))
        if src is None or tgt is None or pred is None:
            continue
        obj = objects_by_id.get(src)
        if obj is None:
            continue
        predicate = str(pred)
        reference = {"@id": _iri(tgt)}
        existing = obj.get(predicate)
        if existing is None:
            obj[predicate] = reference
        elif isinstance(existing, list):
            existing.append(reference)
        else:
            obj[predicate] = [existing, reference]


def to_jsonld(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
) -> JsonLdGraph:
    """Assemble node/edge dicts into a :class:`JsonLdGraph` (§22.6).

    Nodes are de-duplicated by ``id`` (first occurrence wins) so the ``@graph``
    length equals the number of unique nodes; :func:`attach_edges` then folds the
    edges into their subjects. ``context`` overrides :data:`DEFAULT_CONTEXT` when
    provided. RU: собираем документ JSON-LD.
    """
    ctx = DEFAULT_CONTEXT if context is None else context
    objects_by_id: dict[Any, dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id")
        if node_id in objects_by_id:
            continue
        objects_by_id[node_id] = node_object(node)
    attach_edges(objects_by_id, edges)
    return JsonLdGraph(context=ctx, graph=tuple(objects_by_id.values()))


def to_json(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> str:
    """Serialize the graph to a JSON-LD text (RU: сериализация в текст JSON).

    ``json.loads`` on the result round-trips back to :meth:`JsonLdGraph.as_dict`.
    """
    return json.dumps(to_jsonld(nodes, edges).as_dict())
