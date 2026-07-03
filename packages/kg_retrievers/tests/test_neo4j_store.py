"""Neo4jGraphStore against the LIVE server (§3.1 / §8) — round-trip + cleanup.

Connects to bolt://localhost:7687 and exercises the drop-in interface on a private
``t_neo4j_<pid>`` namespace, DETACH-DELETEd in teardown. Skips only if bolt is
genuinely unreachable (never to hide a real failure).
"""

from __future__ import annotations

import os

import pytest

from kg_common import GraphNode
from kg_retrievers.neo4j_store import Neo4jGraphStore

_URI = "bolt://localhost:7687"
_AUTH = ("neo4j", "password")
# pid-derived token (NOT the random module) → isolated, reproducible namespace.
_PREFIX = f"t_neo4j_{os.getpid()}"


def _nid(suffix: str) -> str:
    return f"{_PREFIX}:{suffix}"


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    try:
        s = Neo4jGraphStore(_URI, *_AUTH)
    except Exception as exc:  # bolt genuinely unreachable
        pytest.skip(f"live Neo4j not reachable at {_URI}: {exc}")
    try:
        yield s
    finally:
        # Purge every node in this test's namespace (edges go with DETACH DELETE).
        s.execute(
            "MATCH (n:Node) WHERE n.id STARTS WITH $p DETACH DELETE n",
            {"p": f"{_PREFIX}:"},
        )
        s.close()


def _seed(s: Neo4jGraphStore) -> None:
    s.upsert_node(
        _nid("ni"),
        "Material",
        name="Никель",
        canonical_name="nickel",
        confidence=1.0,
        custom_field="xyz",
    )
    s.upsert_node(
        _nid("ew"),
        "ProcessingRegime",
        name="electrowinning 60C",
        operation="electrowinning",
        temperature_c=60.0,
        confidence=0.9,
    )
    s.upsert_edge(_nid("ew"), _nid("ni"), "APPLIES_TO", confidence=0.8, evidence_ids=["ev:1"])


def test_node_roundtrip_native_prop(store: Neo4jGraphStore) -> None:
    store.upsert_node(_nid("cu"), "Material", name="Copper", formula="Cu", custom_field="xyz")
    nd = store.get_node(_nid("cu"))
    assert nd is not None
    assert nd["id"] == _nid("cu")
    assert nd["name"] == "Copper"
    assert nd["formula"] == "Cu"  # native property, not a JSON blob
    assert nd["custom_field"] == "xyz"


def test_get_missing_returns_none(store: Neo4jGraphStore) -> None:
    assert store.get_node(_nid("does_not_exist")) is None


def test_upsert_idempotent_counts(store: Neo4jGraphStore) -> None:
    before = store.counts()["nodes"]
    _seed(store)
    _seed(store)  # run twice — MERGE must not duplicate
    after = store.counts()["nodes"]
    assert after == before + 2  # exactly the two seeded nodes


def test_upsert_node_guarded_protects_reviewed(store: Neo4jGraphStore) -> None:
    store.upsert_node(_nid("r"), "Material", name="orig", review_status="accepted")
    assert store.upsert_node_guarded(_nid("r"), "Material", name="changed") is False
    assert store.get_node(_nid("r"))["name"] == "orig"


def test_edge_and_edges_among(store: Neo4jGraphStore) -> None:
    _seed(store)
    edges = store.edges_among({_nid("ew"), _nid("ni")})
    assert len(edges) == 1
    e = edges[0]
    assert e.type == "APPLIES_TO"
    assert e.source == _nid("ew") and e.target == _nid("ni")
    assert e.confidence == pytest.approx(0.8)
    assert e.evidence_ids == ["ev:1"]  # native list handled


def test_neighbors_payload(store: Neo4jGraphStore) -> None:
    _seed(store)
    resp = store.neighbors(_nid("ew"), depth=1)
    ids = {n.id for n in resp.nodes}
    assert {_nid("ew"), _nid("ni")} <= ids  # seed + neighbour
    assert any(e.type == "APPLIES_TO" for e in resp.edges)


def test_counts_by_label(store: Neo4jGraphStore) -> None:
    _seed(store)
    by = store.counts_by_label()
    assert by.get("Material", 0) >= 1
    assert by.get("ProcessingRegime", 0) >= 1


def test_node_to_dto_shape(store: Neo4jGraphStore) -> None:
    store.upsert_node(_nid("dto"), "Material", name="Iron", confidence=0.77, verified=True)
    dto = store.node_to_dto(store.get_node(_nid("dto")))
    assert isinstance(dto, GraphNode)
    assert dto.id == _nid("dto")
    assert dto.label == "Iron"  # name wins over id
    assert dto.type == "Material"
    assert dto.confidence == pytest.approx(0.77)
    assert dto.verified is True
    assert "name" not in (dto.properties or {})  # name is promoted out of props


def test_bulk_upsert_nodes(store: Neo4jGraphStore) -> None:
    rows = [(_nid(f"b{i}"), "Bulk", {"name": f"n{i}", "idx": i}) for i in range(5)]
    store.bulk_upsert_nodes(rows)
    for i in range(5):
        nd = store.get_node(_nid(f"b{i}"))
        assert nd is not None and nd["idx"] == i
    assert store.counts_by_label().get("Bulk", 0) >= 5


def test_delete_node(store: Neo4jGraphStore) -> None:
    store.upsert_node(_nid("del"), "Material", name="temp")
    assert store.get_node(_nid("del")) is not None
    store.delete_node(_nid("del"))
    assert store.get_node(_nid("del")) is None


def test_rows_returns_native_node(store: Neo4jGraphStore) -> None:
    _seed(store)
    rows = store.rows("MATCH (n:Node {id:$id}) RETURN n", {"id": _nid("ni")})
    assert len(rows) == 1
    node = rows[0][0]  # returned node stays a neo4j Node object
    assert node["id"] == _nid("ni")
    assert "Node" in node.labels
