"""Experiments router tests (§14.8). Hermetic: a fake graph store stands in.

The router is self-mounted onto a bare FastAPI app (``routers/__init__`` is not
wired yet), and :data:`api_gateway.routers.experiments.get_store` is monkeypatched
to a small fake exposing ``.rows()`` / ``.get_node()`` / ``.upsert_node()`` over
canned Experiment rows — no Kuzu, no LLM. Every assertion checks concrete values.
"""

from __future__ import annotations

import csv
import io

import api_gateway.routers.experiments as experiments
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeStore:
    """Canned Experiment subgraph honouring the router's read-templates (§14.8)."""

    def __init__(self) -> None:
        self.experiments: dict[str, dict] = {
            "exp:1": {
                "label": "Experiment",
                "name": "RO desalination trial",
                "domain": "water_treatment",
                "operation": "reverse_osmosis",
                "review_status": "accepted",
            },
            "exp:2": {
                "label": "Experiment",
                "name": "Ni electrowinning run",
                "domain": "electrometallurgy",
                "operation": "electrowinning",
            },
            "exp:3": {
                "label": "Experiment",
                "name": "Flash smelting test",
                "domain": "pyrometallurgy",
            },
            "not-an-exp": {"label": "Material", "name": "Никель"},
        }
        self.materials: dict[str, list[tuple[str, str]]] = {
            "exp:1": [("mat:water", "Оборотная вода")],
            "exp:2": [("mat:ni", "Никель")],
            "exp:3": [("mat:conc", "Медный концентрат")],
        }
        self.measurements: dict[str, list[tuple]] = {
            "exp:1": [
                ("ms:1", "Эффективность", "removal_efficiency", 95.0, "percent"),
                ("ms:2", "Сульфаты", "concentration", 280.0, "mg/L"),
            ],
            "exp:2": [("ms:3", "Плотность тока", "current_density", 250.0, "A/m^2")],
            "exp:3": [
                ("ms:4", "L(Cu) 1", "distribution_coefficient", 25.0, "ratio"),
                ("ms:5", "L(Cu) 2", "distribution_coefficient", 24.0, "ratio"),
                ("ms:6", "L(Cu) 3", "distribution_coefficient", 26.0, "ratio"),
            ],
        }
        self.evidence_counts: dict[str, int] = {"exp:1": 1, "exp:2": 0, "exp:3": 2}
        self.upserts: list[tuple[str, str, dict]] = []

    def get_node(self, node_id: str) -> dict | None:
        node = self.experiments.get(node_id)
        return None if node is None else {"id": node_id, **node}

    def upsert_node(self, node_id: str, label: str, **props: object) -> None:
        self.upserts.append((node_id, label, props))

    def rows(self, cypher: str, params: dict | None = None) -> list[list]:
        params = params or {}
        if "collect(DISTINCT m.name)" in cypher:  # the aggregate list template
            out: list[list] = []
            for eid, node in self.experiments.items():
                if node["label"] != "Experiment":
                    continue
                mats = [m[1] for m in self.materials.get(eid, [])]
                props = sorted({m[2] for m in self.measurements.get(eid, [])})
                out.append(
                    [
                        eid,
                        node["label"],
                        node["name"],
                        node["domain"],
                        mats,
                        len(self.measurements.get(eid, [])),
                        props,
                    ]
                )
            return out
        eid = params.get("e")
        if "USED_MATERIAL" in cypher:
            return [[m[0], m[1]] for m in self.materials.get(eid, [])]
        if "HAS_MEASUREMENT" in cypher:
            return [list(m) for m in self.measurements.get(eid, [])]
        if "SUPPORTED_BY" in cypher:
            return [[self.evidence_counts.get(eid, 0)]]
        return []


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(experiments, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(experiments.router)
    return TestClient(app)


def test_list_returns_items_and_pagination(client: TestClient) -> None:
    body = client.get("/api/v1/experiments").json()
    assert body["total"] == 3
    assert body["count"] == 3
    assert body["limit"] == 50 and body["offset"] == 0
    ids = {it["id"] for it in body["items"]}
    assert ids == {"exp:1", "exp:2", "exp:3"}


def test_list_item_shape(client: TestClient) -> None:
    items = client.get("/api/v1/experiments").json()["items"]
    exp1 = next(it for it in items if it["id"] == "exp:1")
    assert set(exp1) == {"id", "label", "name", "domain", "material", "n_measurements"}
    assert exp1["label"] == "Experiment"
    assert exp1["name"] == "RO desalination trial"
    assert exp1["domain"] == "water_treatment"
    assert exp1["material"] == "Оборотная вода"
    assert exp1["n_measurements"] == 2


def test_list_pagination_slices(client: TestClient) -> None:
    page1 = client.get("/api/v1/experiments", params={"limit": 2, "offset": 0}).json()
    assert page1["total"] == 3 and page1["count"] == 2 and len(page1["items"]) == 2
    page2 = client.get("/api/v1/experiments", params={"limit": 2, "offset": 2}).json()
    assert page2["total"] == 3 and page2["count"] == 1 and len(page2["items"]) == 1
    first_ids = {it["id"] for it in page1["items"]}
    assert page2["items"][0]["id"] not in first_ids  # non-overlapping window


def test_list_filters(client: TestClient) -> None:
    by_domain = client.get("/api/v1/experiments", params={"domain": "electrometallurgy"}).json()
    assert [it["id"] for it in by_domain["items"]] == ["exp:2"]
    by_material = client.get("/api/v1/experiments", params={"material": "Никель"}).json()
    assert [it["id"] for it in by_material["items"]] == ["exp:2"]
    by_prop = client.get(
        "/api/v1/experiments", params={"property": "distribution_coefficient"}
    ).json()
    assert [it["id"] for it in by_prop["items"]] == ["exp:3"]


def test_query_post_matches_list(client: TestClient) -> None:
    body = {"filters": {"domain": "pyrometallurgy"}, "limit": 10, "offset": 0}
    res = client.post("/api/v1/experiments/query", json=body).json()
    assert res["total"] == 1
    assert res["items"][0]["id"] == "exp:3"
    assert res["items"][0]["n_measurements"] == 3


def test_detail_shape(client: TestClient) -> None:
    d = client.get("/api/v1/experiments/exp:1").json()
    assert d["id"] == "exp:1"
    assert d["label"] == "Experiment"
    assert d["operation"] == "reverse_osmosis"
    assert d["materials"] == [{"id": "mat:water", "name": "Оборотная вода"}]
    assert d["n_measurements"] == 2
    assert {m["property"] for m in d["measurements"]} == {"removal_efficiency", "concentration"}
    assert d["evidence_count"] == 1


def test_detail_missing_404(client: TestClient) -> None:
    assert client.get("/api/v1/experiments/exp:404").status_code == 404
    # a non-Experiment node id must not be served as an experiment either
    assert client.get("/api/v1/experiments/not-an-exp").status_code == 404


def test_export_csv_has_header(client: TestClient) -> None:
    r = client.get("/api/v1/experiments/exp:1/export", params={"format": "csv"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    lines = r.text.splitlines()
    assert lines[0] == "id,name,property,value,unit"
    parsed = list(csv.reader(io.StringIO(r.text)))
    assert parsed[0] == ["id", "name", "property", "value", "unit"]
    assert len(parsed) == 3  # header + 2 measurements
    assert parsed[1][0] == "ms:1" and parsed[1][2] == "removal_efficiency"


def test_export_json_shape(client: TestClient) -> None:
    r = client.get("/api/v1/experiments/exp:3/export", params={"format": "json"})
    assert r.status_code == 200
    body = r.json()
    assert body["experiment_id"] == "exp:3"
    assert body["count"] == 3
    assert body["measurements"][0] == {
        "id": "ms:4",
        "name": "L(Cu) 1",
        "property": "distribution_coefficient",
        "value": 25.0,
        "unit": "ratio",
    }


def test_export_bad_format_400(client: TestClient) -> None:
    r = client.get("/api/v1/experiments/exp:1/export", params={"format": "xml"})
    assert r.status_code == 400


def test_verify_forbidden_for_researcher(client: TestClient, store: FakeStore) -> None:
    r = client.post("/api/v1/experiments/exp:1/verify", headers={"X-Role": "researcher"})
    assert r.status_code == 403
    assert store.upserts == []  # nothing stamped on a rejected call


def test_verify_ok_for_curator(client: TestClient, store: FakeStore) -> None:
    r = client.post("/api/v1/experiments/exp:1/verify", headers={"X-Role": "curator"})
    assert r.status_code == 200
    assert r.json() == {"id": "exp:1", "verified": True}
    assert store.upserts == [("exp:1", "Experiment", {"verified": True})]
