"""Tests for the GraphRAG community-view graph payload (§11.8 / §5.3).

Builds a small deterministic Kuzu store with two communities — one holding many member
entities (to exercise the ``max_entities`` cap) plus a Finding summary artifact, and a
child community — then hand-checks the Reagraph-shaped payload: community/entity node
counts and types, one INCLUDES_ENTITY edge per entity, HAS_SUBCOMMUNITY hierarchy edges,
edge-endpoint integrity, the empty-input case, and JSON-serialisability of as_dict().
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_retrievers.community_view_payload import (
    CommunityViewPayload,
    build_community_view,
    community_node_id,
    entity_node_id,
)
from kg_retrievers.graph_store import KuzuGraphStore

_PARENT = 5  # community with member entities + a Finding artifact
_CHILD = 6  # sub-community of _PARENT
_N_MEMBERS = 10  # more than the default max_entities (8), to exercise the cap


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    # -- community 5: 10 material members (ids ent-00 .. ent-09) --
    for i in range(_N_MEMBERS):
        s.upsert_node(f"ent-{i:02d}", "Material", name=f"Материал {i}", community_id=_PARENT)
    # Finding summary artifact — a report, not a member entity (must be excluded).
    s.upsert_node("find-5", "Finding", name="Cluster #5", text="summary", community_id=_PARENT)
    # -- community 6: one member --
    s.upsert_node("ent-child", "Property", name="Твёрдость", community_id=_CHILD)
    yield s
    s.close()


def test_two_used_ids_yield_two_community_nodes(store: KuzuGraphStore) -> None:
    payload = build_community_view(store, [_PARENT, _CHILD])
    community_nodes = [n for n in payload.nodes if n["type"] == "community"]
    assert len(community_nodes) == 2
    ids = {n["id"] for n in community_nodes}
    assert ids == {community_node_id(_PARENT), community_node_id(_CHILD)}
    assert all(n["label"].startswith("Community ") for n in community_nodes)


def test_entity_nodes_capped_at_max_entities(store: KuzuGraphStore) -> None:
    payload = build_community_view(store, [_PARENT], max_entities=8)
    entity_nodes = [n for n in payload.nodes if n["type"] == "entity"]
    # 10 members exist, but the cap is 8; the Finding artifact is never an entity node.
    assert len(entity_nodes) == 8
    # Deterministic: sorted by id, so the first 8 (ent-00 .. ent-07) are kept.
    expected = {entity_node_id(f"ent-{i:02d}") for i in range(8)}
    assert {n["id"] for n in entity_nodes} == expected
    assert not any(n["id"] == entity_node_id("find-5") for n in payload.nodes)


def test_each_entity_has_exactly_one_includes_edge(store: KuzuGraphStore) -> None:
    payload = build_community_view(store, [_PARENT], max_entities=8)
    inc = [e for e in payload.edges if e["type"] == "INCLUDES_ENTITY"]
    assert len(inc) == 8
    cnode = community_node_id(_PARENT)
    for i in range(8):
        enode = entity_node_id(f"ent-{i:02d}")
        matches = [e for e in inc if e["target"] == enode]
        assert len(matches) == 1
        assert matches[0]["source"] == cnode


def test_subcommunities_yield_has_subcommunity_edges(store: KuzuGraphStore) -> None:
    payload = build_community_view(store, [_PARENT, _CHILD], subcommunities={_PARENT: [_CHILD]})
    sub = [e for e in payload.edges if e["type"] == "HAS_SUBCOMMUNITY"]
    assert len(sub) == 1
    assert sub[0]["source"] == community_node_id(_PARENT)
    assert sub[0]["target"] == community_node_id(_CHILD)


def test_subcommunity_edge_to_unused_child_is_dropped(store: KuzuGraphStore) -> None:
    # Child 99 has no community node (not in used ids) -> no dangling edge.
    payload = build_community_view(store, [_PARENT], subcommunities={_PARENT: [99]})
    assert not any(e["type"] == "HAS_SUBCOMMUNITY" for e in payload.edges)


def test_all_edge_endpoints_reference_existing_nodes(store: KuzuGraphStore) -> None:
    payload = build_community_view(
        store, [_PARENT, _CHILD], max_entities=8, subcommunities={_PARENT: [_CHILD]}
    )
    node_ids = {n["id"] for n in payload.nodes}
    assert node_ids  # non-empty
    for e in payload.edges:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


def test_empty_used_ids_yield_empty_payload(store: KuzuGraphStore) -> None:
    payload = build_community_view(store, [], subcommunities={_PARENT: [_CHILD]})
    assert payload.nodes == ()
    assert payload.edges == ()
    assert payload.as_dict() == {"nodes": [], "edges": []}


def test_as_dict_is_json_serializable_str_list_dict(store: KuzuGraphStore) -> None:
    payload = build_community_view(
        store, [_PARENT, _CHILD], max_entities=8, subcommunities={_PARENT: [_CHILD]}
    )
    d = payload.as_dict()
    assert set(d) == {"nodes", "edges"}
    assert isinstance(d["nodes"], list) and isinstance(d["edges"], list)
    # Round-trips through JSON, and every scalar value is a str.
    reloaded = json.loads(json.dumps(d))
    assert reloaded == d
    for item in d["nodes"] + d["edges"]:
        assert isinstance(item, dict)
        for v in item.values():
            assert isinstance(v, str)


def test_as_dict_copies_do_not_mutate_payload(store: KuzuGraphStore) -> None:
    payload = build_community_view(store, [_PARENT], max_entities=2)
    d = payload.as_dict()
    d["nodes"].append({"id": "x", "label": "x", "type": "entity"})
    d["nodes"][0]["type"] = "tampered"
    assert len(payload.nodes) == 3  # 1 community + 2 entities, unchanged
    assert payload.nodes[0]["type"] == "community"


def test_payload_type_and_default_empty() -> None:
    payload = CommunityViewPayload()
    assert payload.nodes == ()
    assert payload.edges == ()
    assert payload.as_dict() == {"nodes": [], "edges": []}
