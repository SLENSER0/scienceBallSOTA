"""Graph-ext router tests (§14.6). Hermetic: a fake graph store stands in.

The router is self-mounted onto a bare FastAPI app (``routers/__init__`` is not
wired yet), and :data:`api_gateway.routers.graph_ext.get_store` (imported from
``api_gateway.deps``) is monkeypatched to a small fake exposing ``.rows()`` /
``.get_node()`` over a canned Al-Cu mini-graph (§6.2 example) — no Kuzu, no LLM.

Canned graph (a directed path with one contradicted branch)::

    mat:al --HAS_REGIME--> reg:aging --HAS_MEASUREMENT--> meas:hv --HAS_GAP--> gap:base

Every assertion checks concrete expected values.
"""

from __future__ import annotations

import re

import api_gateway.routers.graph_ext as graph_ext
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# id -> full property bag (what get_node returns; props already merged, §14.6 note).
_NODES: dict[str, dict] = {
    "mat:al": {
        "id": "mat:al",
        "label": "Material",
        "name": "Al-Cu 2024",
        "confidence": 0.9,
        "verified": True,
        "evidence_count": 3,
        "missing_fields": [],
    },
    "reg:aging": {
        "id": "reg:aging",
        "label": "ProcessingRegime",
        "name": "Aging 180C 2h",
        "confidence": 0.8,
        "verified": False,
        "evidence_count": 1,
    },
    "meas:hv": {
        "id": "meas:hv",
        "label": "Measurement",
        "name": "Vickers 148 HV",
        "confidence": 0.75,
        "missing_fields": ["unit"],
    },
    "gap:base": {
        "id": "gap:base",
        "label": "Gap",
        "name": "missing_baseline",
        "gap_type": "missing_baseline",
    },
}

# (src, type, dst, confidence, evidence_ids, contradicted, inferred)
_EDGES: list[tuple] = [
    ("mat:al", "HAS_REGIME", "reg:aging", 0.9, ["ev:1"], False, False),
    ("reg:aging", "HAS_MEASUREMENT", "meas:hv", 0.8, ["ev:2", "ev:3"], False, True),
    ("meas:hv", "HAS_GAP", "gap:base", 0.5, [], True, False),
]


class FakeStore:
    """Read-only fake honouring the graph_ext read-templates (§14.6)."""

    def __init__(self) -> None:
        self.nodes = {k: dict(v) for k, v in _NODES.items()}
        self.edges = list(_EDGES)

    def get_node(self, node_id: str) -> dict | None:
        node = self.nodes.get(node_id)
        return None if node is None else dict(node)

    def rows(self, cypher: str, params: dict | None = None) -> list[list]:
        params = params or {}
        if "RETURN DISTINCT b.id" in cypher:  # expansion (undirected BFS to depth)
            return self._expand(cypher, params)
        if "RETURN a.id, r.type, b.id" in cypher:  # edges among a resolved id set
            return self._edges(params)
        if "RETURN n.id" in cypher:  # candidate node selection by id/label filter
            return self._select(params)
        return []

    # -- template implementations ------------------------------------------
    def _select(self, params: dict) -> list[list]:
        node_ids = params.get("node_ids")
        labels = params.get("labels")
        out: list[list] = []
        for nid, node in self.nodes.items():
            if node_ids is not None and nid not in node_ids:
                continue
            if labels and node.get("label") not in labels:
                continue
            out.append([nid])
        return out

    def _edges(self, params: dict) -> list[list]:
        ids = set(params.get("ids") or [])
        rel_types = params.get("rel_types")
        out: list[list] = []
        for src, rtype, dst, conf, eids, contra, inferred in self.edges:
            if src not in ids or dst not in ids:
                continue
            if rel_types and rtype not in rel_types:
                continue
            out.append([src, rtype, dst, conf, list(eids), contra, inferred])
        return out

    def _expand(self, cypher: str, params: dict) -> list[list]:
        depth = int(re.search(r"\*1\.\.(\d+)", cypher).group(1))
        types = params.get("types")
        adj: dict[str, set[str]] = {}
        for src, _t, dst, *_rest in self.edges:  # undirected adjacency
            adj.setdefault(src, set()).add(dst)
            adj.setdefault(dst, set()).add(src)
        seeds = list(params.get("ids") or [])
        reached: set[str] = set()
        frontier = set(seeds)
        for _ in range(depth):
            nxt: set[str] = set()
            for nid in frontier:
                nxt |= adj.get(nid, set())
            reached |= nxt
            frontier = nxt
        found = [n for n in reached if n not in seeds]  # b at distance >= 1
        if types:
            found = [n for n in found if self.nodes.get(n, {}).get("label") in types]
        return [[n] for n in found]


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(graph_ext, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(graph_ext.router)
    return TestClient(app)


_NODE_KEYS = {"id", "label", "type", "confidence", "evidenceCount", "verified", "missingFields"}
_EDGE_KEYS = {
    "id",
    "source",
    "target",
    "type",
    "confidence",
    "inferred",
    "contradicted",
    "evidenceIds",
}


def test_query_returns_graph_shape(client: TestClient) -> None:
    body = client.post("/api/v1/graph/query", json={"node_ids": ["mat:al", "reg:aging"]}).json()
    assert body["truncated"] is False
    assert {n["id"] for n in body["nodes"]} == {"mat:al", "reg:aging"}
    for node in body["nodes"]:
        assert set(node) == _NODE_KEYS
    mat = next(n for n in body["nodes"] if n["id"] == "mat:al")
    assert mat["label"] == "Al-Cu 2024"  # display name, not the id
    assert mat["type"] == "Material"  # ontology label
    assert mat["confidence"] == 0.9
    assert mat["evidenceCount"] == 3
    assert mat["verified"] is True
    assert mat["missingFields"] == []
    # exactly the HAS_REGIME edge is internal to the {mat:al, reg:aging} set
    assert len(body["edges"]) == 1
    edge = body["edges"][0]
    assert set(edge) == _EDGE_KEYS
    assert edge["id"] == "mat:al|HAS_REGIME|reg:aging"
    assert (edge["source"], edge["target"], edge["type"]) == ("mat:al", "reg:aging", "HAS_REGIME")
    assert edge["evidenceIds"] == ["ev:1"]
    assert edge["inferred"] is False and edge["contradicted"] is False


def test_query_no_filter_returns_whole_graph(client: TestClient) -> None:
    body = client.post("/api/v1/graph/query", json={}).json()
    assert {n["id"] for n in body["nodes"]} == {"mat:al", "reg:aging", "meas:hv", "gap:base"}
    assert len(body["edges"]) == 3  # all three edges are internal now
    assert body["truncated"] is False
    # the inferred / contradicted encodings survive round-trip
    inferred = next(e for e in body["edges"] if e["type"] == "HAS_MEASUREMENT")
    assert inferred["inferred"] is True and inferred["evidenceIds"] == ["ev:2", "ev:3"]
    contradicted = next(e for e in body["edges"] if e["type"] == "HAS_GAP")
    assert contradicted["contradicted"] is True and contradicted["evidenceIds"] == []


def test_query_label_filter(client: TestClient) -> None:
    body = client.post("/api/v1/graph/query", json={"labels": ["Material"]}).json()
    assert [n["id"] for n in body["nodes"]] == ["mat:al"]
    assert body["edges"] == []  # a single node has no internal edges
    assert body["truncated"] is False


def test_query_rel_types_filter(client: TestClient) -> None:
    body = client.post(
        "/api/v1/graph/query",
        json={"node_ids": ["mat:al", "reg:aging", "meas:hv"], "rel_types": ["HAS_REGIME"]},
    ).json()
    assert {e["type"] for e in body["edges"]} == {"HAS_REGIME"}
    assert len(body["edges"]) == 1


def test_query_caps_truncate_nodes(client: TestClient) -> None:
    body = client.post("/api/v1/graph/query", json={"max_nodes": 1}).json()
    assert len(body["nodes"]) == 1  # capped from 4 down to 1
    assert body["truncated"] is True


def test_query_caps_truncate_edges(client: TestClient) -> None:
    body = client.post(
        "/api/v1/graph/query",
        json={"node_ids": ["mat:al", "reg:aging", "meas:hv", "gap:base"], "max_edges": 1},
    ).json()
    assert len(body["edges"]) == 1  # capped from 3 down to 1
    assert body["truncated"] is True


def test_query_empty_node_ids_is_empty_graph(client: TestClient) -> None:
    body = client.post("/api/v1/graph/query", json={"node_ids": []}).json()
    assert body == {"nodes": [], "edges": [], "truncated": False}


def test_query_invalid_body_422(client: TestClient) -> None:
    r = client.post("/api/v1/graph/query", json={"max_nodes": "not-an-int"})
    assert r.status_code == 422


def test_expand_returns_neighbors_of_seed(client: TestClient) -> None:
    body = client.post("/api/v1/graph/expand", json={"node_ids": ["mat:al"], "depth": 1}).json()
    assert {n["id"] for n in body["nodes"]} == {"mat:al", "reg:aging"}  # seed + 1-hop
    assert len(body["edges"]) == 1
    assert body["edges"][0]["id"] == "mat:al|HAS_REGIME|reg:aging"
    assert body["truncated"] is False


def test_expand_two_hop(client: TestClient) -> None:
    body = client.post("/api/v1/graph/expand", json={"node_ids": ["mat:al"], "depth": 2}).json()
    assert {n["id"] for n in body["nodes"]} == {"mat:al", "reg:aging", "meas:hv"}
    assert {e["type"] for e in body["edges"]} == {"HAS_REGIME", "HAS_MEASUREMENT"}


def test_expand_types_filter(client: TestClient) -> None:
    body = client.post(
        "/api/v1/graph/expand",
        json={"node_ids": ["mat:al"], "depth": 2, "types": ["Measurement"]},
    ).json()
    # only the Measurement neighbour survives the type filter (plus the seed)
    assert {n["id"] for n in body["nodes"]} == {"mat:al", "meas:hv"}


def test_expand_empty_node_ids_is_empty_graph(client: TestClient) -> None:
    body = client.post("/api/v1/graph/expand", json={"node_ids": []}).json()
    assert body == {"nodes": [], "edges": [], "truncated": False}


def test_expand_missing_node_ids_422(client: TestClient) -> None:
    assert client.post("/api/v1/graph/expand", json={}).status_code == 422


def test_expand_invalid_depth_422(client: TestClient) -> None:
    r = client.post("/api/v1/graph/expand", json={"node_ids": ["mat:al"], "depth": "deep"})
    assert r.status_code == 422
