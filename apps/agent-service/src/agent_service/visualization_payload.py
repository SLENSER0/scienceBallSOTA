"""Full §5.3 GraphResponse builder — adds ``layoutHints`` + ``queryContext`` (§5.3/§5.2.3).

Сборщик полного ``GraphResponse`` (§5.3). Слой ``kg_retrievers.graph_dto.
build_graph_response`` кодирует только ``nodes``/``edges`` и намеренно оставляет
``layoutHints``/``queryContext`` вышестоящим слоям — этот модуль их и добавляет.

Это чистый, детерминированный слой (no DB, no I/O): на вход — уже прочитанный из
графа ``dict`` (``{"nodes": [...], "edges": [...]}``), список резолвленных сущностей,
исполненные Cypher-запросы и контекст пользовательского запроса; на выход — JSON-ready
``dict`` с camelCase-ключами ``nodes``/``edges``/``layoutHints``/``queryContext``,
совпадающими с TS-типами фронтенда и Pydantic-DTO ``kg_common.dto.GraphResponse``.

``layoutHints`` (§5.3): ``rootNodeIds`` — canonical_id резолвленных сущностей (корни
раскладки Reagraph), ``communities`` — id сообществ (§8) для группировки. ``queryContext``
(§5.3): исходный ``userQuery``, применённые ``filters`` и ``generatedCypher`` — последний
исполненный Cypher (§3.14), для отладки/воспроизводимости.

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN base
columns and read the rest via ``get_node``; by the time the graph ``dict`` reaches this
module it already carries the merged props, so nothing here touches the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kg_retrievers.graph_dto import build_graph_response


@dataclass(frozen=True)
class VizPayload:
    """Full §5.3 GraphResponse: encoded nodes/edges plus layout + query context."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    layout_hints: dict[str, Any] = field(default_factory=dict)
    query_context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.3 GraphResponse camelCase payload (copies containers)."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "layoutHints": dict(self.layout_hints),
            "queryContext": dict(self.query_context),
        }


def _root_node_ids(entities: list[dict[str, Any]]) -> list[str]:
    """canonical_id of each resolved entity (non-null ``canonical_id``) — §5.3 roots."""
    roots: list[str] = []
    for entity in entities:
        canonical_id = entity.get("canonical_id")
        if canonical_id is not None:
            roots.append(str(canonical_id))
    return roots


def build_visualization_payload(
    retrieved_graph: dict[str, Any],
    entities: list[dict[str, Any]],
    cypher_queries: list[str],
    user_query: str,
    filters: dict[str, Any],
    communities: list[str] | None = None,
) -> VizPayload:
    """Assemble the full §5.3 GraphResponse (nodes/edges + layoutHints/queryContext).

    Node/edge encoding is delegated to :func:`kg_retrievers.graph_dto.build_graph_response`
    (the §5.2.3 visual-encoding layer) over ``retrieved_graph["nodes"]``/``["edges"]``.
    ``layoutHints`` gets ``rootNodeIds`` = canonical_ids of resolved entities (those with
    a non-null ``canonical_id``) and ``communities`` (passthrough, ``[]`` if ``None``).
    ``queryContext`` gets the raw ``userQuery``, applied ``filters`` and ``generatedCypher``
    = the LAST executed Cypher query (or ``None`` when no queries were run, §3.14).
    """
    graph = build_graph_response(
        retrieved_graph.get("nodes", []),
        retrieved_graph.get("edges", []),
    )
    layout_hints = {
        "rootNodeIds": _root_node_ids(entities),
        "communities": list(communities) if communities else [],
    }
    query_context = {
        "userQuery": user_query,
        "filters": filters,
        "generatedCypher": cypher_queries[-1] if cypher_queries else None,
    }
    return VizPayload(
        nodes=graph["nodes"],
        edges=graph["edges"],
        layout_hints=layout_hints,
        query_context=query_context,
    )
