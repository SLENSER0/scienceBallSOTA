"""Node/edge dicts → replayable Cypher CREATE dump (§22.6).

Чистый детерминированный сериализатор (no DB, no I/O): превращает обычные ``dict``
узлов и рёбер в воспроизводимый Cypher-скрипт — сначала ``CREATE`` всех узлов, затем
``MATCH .. CREATE`` рёбер, связанных по свойству ``id``. Обратная сторона экспорта
графа: результат можно проиграть в пустой базе и получить тот же граф.

Pure-python serializer producing a replayable Cypher CREATE dump. Nodes are emitted
first (``CREATE (:Label {props});``), relationships second, each keyed by the ``id``
property of its endpoints (``MATCH (a {id: ..}), (b {id: ..}) CREATE (a)-[:T]->(b);``).

Values (§22.6): ``str`` is single-quote-escaped, ``int``/``float`` bare, ``bool`` as
``true``/``false``, ``None`` omitted from the property map entirely.

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN base
columns and read the rest via ``get_node``; by the time a node/edge ``dict`` reaches
this module it already carries the merged props, so nothing here touches the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Default node label when a node dict carries no ``label`` (§22.6 assertion 7).
DEFAULT_LABEL = "Node"

# Default relationship type when an edge dict carries no ``type``.
DEFAULT_REL_TYPE = "REL"

# Edge keys consumed as structure (endpoints + type); everything else is a rel prop.
_RESERVED_EDGE_KEYS: frozenset[str] = frozenset({"source", "target", "type"})


def _cypher_value(value: Any) -> str | None:
    """Render one property value as a Cypher literal, or ``None`` to omit it (§22.6).

    ``None`` → ``None`` (caller omits the key); ``bool`` → ``true``/``false`` (checked
    before ``int``, since ``bool`` is an ``int`` subclass); ``int``/``float`` bare;
    everything else stringified and single-quote-escaped (``\\`` and ``'`` backslashed).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _props_map(props: dict[str, Any]) -> str:
    """Render a ``dict`` as a Cypher ``{k: v, ...}`` map, omitting ``None`` values."""
    parts: list[str] = []
    for key, value in props.items():
        rendered = _cypher_value(value)
        if rendered is None:
            continue
        parts.append(f"{key}: {rendered}")
    return "{" + ", ".join(parts) + "}"


def node_create(node: dict[str, Any]) -> str:
    """Serialize one node ``dict`` to a ``CREATE (:Label {props});`` statement.

    The ``label`` key selects the Cypher node label (default :data:`DEFAULT_LABEL`); all
    other keys become properties, in the node's own key order (so an ``id``-first dict
    yields ``{id: .., name: ..}``). ``None``-valued props are omitted from the map.
    """
    label = node.get("label") or DEFAULT_LABEL
    props = {key: value for key, value in node.items() if key != "label"}
    return f"CREATE (:{label} {_props_map(props)});"


def rel_create(edge: dict[str, Any]) -> str:
    """Serialize one edge ``dict`` to a ``MATCH .. CREATE`` relationship statement.

    Endpoints are matched by their ``id`` property (``source``/``target`` hold the id
    values); ``type`` is the RelType (default :data:`DEFAULT_REL_TYPE`). Any remaining
    keys become relationship properties rendered inside the arrow (``[:T {props}]``).
    """
    src = _cypher_value(edge.get("source"))
    tgt = _cypher_value(edge.get("target"))
    rel_type = edge.get("type") or DEFAULT_REL_TYPE
    props = {key: value for key, value in edge.items() if key not in _RESERVED_EDGE_KEYS}
    rel_props = _props_map(props) if props else ""
    rel_body = f":{rel_type}" + (f" {rel_props}" if rel_props else "")
    match = f"MATCH (a {{id: {src}}}), (b {{id: {tgt}}})"
    return f"{match} CREATE (a)-[{rel_body}]->(b);"


@dataclass(frozen=True)
class CypherDump:
    """A replayable Cypher CREATE dump: node stmts, rel stmts, and the joined script."""

    node_stmts: tuple[str, ...]
    rel_stmts: tuple[str, ...]
    script: str

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready ``dict`` (tuples → lists)."""
        return {
            "node_stmts": list(self.node_stmts),
            "rel_stmts": list(self.rel_stmts),
            "script": self.script,
        }


def to_cypher(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> CypherDump:
    """Build a :class:`CypherDump` from raw nodes/edges (nodes first, then rels).

    Node ``CREATE`` statements always precede relationship ``MATCH .. CREATE`` ones so the
    script replays cleanly (endpoints exist before edges reference them). Empty inputs
    yield empty tuples and an empty ``script``.
    """
    node_stmts = tuple(node_create(node) for node in nodes)
    rel_stmts = tuple(rel_create(edge) for edge in edges)
    script = "\n".join(node_stmts + rel_stmts)
    return CypherDump(node_stmts=node_stmts, rel_stmts=rel_stmts, script=script)


def script_text(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Return just the replayable Cypher script text for ``nodes``/``edges`` (§22.6)."""
    return to_cypher(nodes, edges).script
