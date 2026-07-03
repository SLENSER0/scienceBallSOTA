"""Tests for the §5.3 visualization_payload builder (layoutHints + queryContext).

Тесты сборщика полного ``GraphResponse`` (§5.3): проверяем rootNodeIds из canonical_id,
generatedCypher = последний Cypher, passthrough сообществ, camelCase-ключи as_dict(),
round-trip фильтров и делегирование кодирования узлов в ``build_graph_response``.

Модуль чистый (no DB): узлы/рёбра приходят как ``dict`` с уже слитыми props, поэтому
временный Kuzu-store не нужен — hand-checkable фикстуры на обычных dict.
"""

from __future__ import annotations

from agent_service.visualization_payload import (
    VizPayload,
    build_visualization_payload,
)

# The nine §5.3 GraphNode camelCase keys every encoded node must carry (§5.2.3).
NODE_KEYS = {
    "id",
    "label",
    "type",
    "confidence",
    "evidenceCount",
    "verified",
    "missingFields",
    "communityId",
    "properties",
}


def _graph() -> dict:
    """A tiny two-node / one-edge graph dict (already store-read, merged props)."""
    return {
        "nodes": [
            {"id": "mat:1", "label": "Material", "name": "Graphene", "confidence": 0.9},
            {"id": "exp:1", "label": "Experiment", "name": "Anneal", "confidence": 0.8},
        ],
        "edges": [
            {"id": "e1", "source": "mat:1", "target": "exp:1", "type": "USED_IN"},
        ],
    }


def _entities() -> list[dict]:
    """Two resolved entities (with canonical_id) and one unresolved (None)."""
    return [
        {"mention": "graphene", "canonical_id": "mat:1"},
        {"mention": "annealing", "canonical_id": "exp:1"},
        {"mention": "unknown widget", "canonical_id": None},
    ]


def test_root_node_ids_are_resolved_canonical_ids() -> None:
    """(1) rootNodeIds == canonical_ids of entities with a non-null canonical_id."""
    payload = build_visualization_payload(
        _graph(),
        _entities(),
        cypher_queries=["MATCH (n) RETURN n"],
        user_query="graphene annealing",
        filters={},
    )
    assert payload.layout_hints["rootNodeIds"] == ["mat:1", "exp:1"]


def test_generated_cypher_is_last_query() -> None:
    """(2) generatedCypher is the LAST cypher query, not the first."""
    payload = build_visualization_payload(
        _graph(),
        _entities(),
        cypher_queries=["MATCH (a) RETURN a", "MATCH (b) RETURN b"],
        user_query="q",
        filters={},
    )
    assert payload.query_context["generatedCypher"] == "MATCH (b) RETURN b"


def test_empty_cypher_queries_gives_none() -> None:
    """(3) empty cypher_queries -> generatedCypher is None."""
    payload = build_visualization_payload(
        _graph(),
        _entities(),
        cypher_queries=[],
        user_query="q",
        filters={},
    )
    assert payload.query_context["generatedCypher"] is None


def test_communities_passthrough_preserved() -> None:
    """(4) communities passthrough preserved verbatim; None -> []."""
    payload = build_visualization_payload(
        _graph(),
        _entities(),
        cypher_queries=["c"],
        user_query="q",
        filters={},
        communities=["c-1", "c-2"],
    )
    assert payload.layout_hints["communities"] == ["c-1", "c-2"]

    none_payload = build_visualization_payload(
        _graph(), _entities(), cypher_queries=[], user_query="q", filters={}
    )
    assert none_payload.layout_hints["communities"] == []


def test_as_dict_has_camelcase_keys() -> None:
    """(5) as_dict() emits camelCase layoutHints and queryContext (plus nodes/edges)."""
    payload = build_visualization_payload(
        _graph(), _entities(), cypher_queries=["c"], user_query="q", filters={}
    )
    out = payload.as_dict()
    assert set(out) == {"nodes", "edges", "layoutHints", "queryContext"}
    assert out["layoutHints"] == payload.layout_hints
    assert out["queryContext"] == payload.query_context


def test_nodes_count_and_nine_keys() -> None:
    """(6) node count equals input, and each node carries the nine §5.3 keys."""
    graph = _graph()
    payload = build_visualization_payload(
        graph, _entities(), cypher_queries=["c"], user_query="q", filters={}
    )
    assert len(payload.nodes) == len(graph["nodes"])
    for node in payload.nodes:
        assert set(node) == NODE_KEYS
    # delegation sanity: display label came from the human ``name``
    assert {n["label"] for n in payload.nodes} == {"Graphene", "Anneal"}
    assert len(payload.edges) == len(graph["edges"])


def test_filters_round_trip_unchanged() -> None:
    """(7) filters dict round-trips into queryContext unchanged (same content)."""
    filters = {"material": "Graphene", "yearRange": [2019, 2024], "verified": True}
    payload = build_visualization_payload(
        _graph(), _entities(), cypher_queries=["c"], user_query="q", filters=filters
    )
    assert payload.query_context["filters"] == filters
    assert payload.as_dict()["queryContext"]["filters"] == filters


def test_user_query_recorded() -> None:
    """queryContext echoes the raw userQuery verbatim."""
    payload = build_visualization_payload(
        _graph(), _entities(), cypher_queries=[], user_query="what is graphene?", filters={}
    )
    assert payload.query_context["userQuery"] == "what is graphene?"


def test_vizpayload_is_frozen() -> None:
    """VizPayload is a frozen dataclass (house style)."""
    payload = VizPayload(nodes=[], edges=[], layout_hints={}, query_context={})
    try:
        payload.nodes = [{"x": 1}]  # type: ignore[misc]
    except Exception as exc:  # dataclasses raises FrozenInstanceError
        assert "FrozenInstance" in type(exc).__name__
    else:
        raise AssertionError("VizPayload should be frozen")


def test_as_dict_copies_top_level_node_and_edge_dicts() -> None:
    """as_dict() re-wraps node/edge dicts so mutating output does not alias payload."""
    payload = build_visualization_payload(
        _graph(), _entities(), cypher_queries=["c"], user_query="q", filters={}
    )
    out = payload.as_dict()
    out["nodes"][0]["label"] = "tampered"
    assert payload.nodes[0]["label"] != "tampered"
