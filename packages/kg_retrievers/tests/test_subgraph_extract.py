"""Ego- and induced-subgraph extraction over a temp KuzuGraphStore (§8.12).

Seed graph (undirected traversal; edges stored directed as written):

    c -> n1 -> n11
    c -> n2 -> n22
    c -> n3

so ``c`` has direct neighbours {n1, n2, n3} (radius 1) and reaches {n11, n22}
at radius 2. All values below are hand-computed against this fixed shape.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.subgraph_extract import ego_subgraph, induced_subgraph


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _seed(s)
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    s.upsert_node("c", "Material", name="center")
    s.upsert_node("n1", "Material", name="near-1", custom_field="keep-me")
    s.upsert_node("n2", "Material", name="near-2")
    s.upsert_node("n3", "Material", name="near-3")
    s.upsert_node("n11", "Material", name="far-1")
    s.upsert_node("n22", "Material", name="far-2")
    s.upsert_edge("c", "n1", "CONNECTED")
    s.upsert_edge("c", "n2", "CONNECTED")
    s.upsert_edge("c", "n3", "CONNECTED")
    s.upsert_edge("n1", "n11", "CONNECTED")
    s.upsert_edge("n2", "n22", "CONNECTED")


def _node_ids(sg: dict[str, Any]) -> set[str]:
    return {n["id"] for n in sg["nodes"]}


def _edge_pairs(sg: dict[str, Any]) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in sg["edges"]}


def test_ego_radius1_includes_neighbours(store: KuzuGraphStore) -> None:
    sg = ego_subgraph(store, "c", radius=1)
    assert _node_ids(sg) == {"c", "n1", "n2", "n3"}
    assert _edge_pairs(sg) == {("c", "n1"), ("c", "n2"), ("c", "n3")}
    assert len(sg["edges"]) == 3


def test_ego_radius2_expands(store: KuzuGraphStore) -> None:
    sg = ego_subgraph(store, "c", radius=2)
    assert _node_ids(sg) == {"c", "n1", "n2", "n3", "n11", "n22"}
    assert _edge_pairs(sg) == {
        ("c", "n1"),
        ("c", "n2"),
        ("c", "n3"),
        ("n1", "n11"),
        ("n2", "n22"),
    }
    assert len(sg["edges"]) == 5


def test_ego_max_nodes_caps(store: KuzuGraphStore) -> None:
    # BFS adds sorted neighbours n1,n2,n3 (centre = 4th) then hits the cap before n11.
    sg = ego_subgraph(store, "c", radius=2, max_nodes=4)
    assert _node_ids(sg) == {"c", "n1", "n2", "n3"}
    assert len(sg["nodes"]) == 4
    assert _edge_pairs(sg) == {("c", "n1"), ("c", "n2"), ("c", "n3")}


def test_ego_edges_only_among_included(store: KuzuGraphStore) -> None:
    # n11 is out of a radius-1 ego, so the n1->n11 edge must be excluded.
    sg = ego_subgraph(store, "c", radius=1)
    assert ("n1", "n11") not in _edge_pairs(sg)
    for e in sg["edges"]:
        assert e["source"] in _node_ids(sg)
        assert e["target"] in _node_ids(sg)


def test_ego_node_payload_carries_props(store: KuzuGraphStore) -> None:
    sg = ego_subgraph(store, "c", radius=1)
    n1 = next(n for n in sg["nodes"] if n["id"] == "n1")
    assert n1["name"] == "near-1"
    assert n1["custom_field"] == "keep-me"  # read from props JSON via get_node


def test_unknown_center_returns_empty(store: KuzuGraphStore) -> None:
    sg = ego_subgraph(store, "ghost", radius=2)
    assert sg == {"nodes": [], "edges": []}


def test_induced_subgraph_over_set(store: KuzuGraphStore) -> None:
    sg = induced_subgraph(store, ["c", "n1", "n2"])
    assert _node_ids(sg) == {"c", "n1", "n2"}
    assert _edge_pairs(sg) == {("c", "n1"), ("c", "n2")}  # c->n3 excluded (n3 not in set)
    assert len(sg["edges"]) == 2


def test_induced_no_edge_between_unconnected(store: KuzuGraphStore) -> None:
    sg = induced_subgraph(store, {"n1", "n2"})
    assert _node_ids(sg) == {"n1", "n2"}
    assert sg["edges"] == []  # n1 and n2 share no direct edge


def test_induced_ignores_unknown_ids(store: KuzuGraphStore) -> None:
    sg = induced_subgraph(store, ["c", "ghost"])
    assert _node_ids(sg) == {"c"}
    assert sg["edges"] == []


def test_induced_edge_direction_preserved(store: KuzuGraphStore) -> None:
    sg = induced_subgraph(store, ["n1", "n11"])
    assert len(sg["edges"]) == 1
    edge = sg["edges"][0]
    assert (edge["source"], edge["target"], edge["type"]) == ("n1", "n11", "CONNECTED")
