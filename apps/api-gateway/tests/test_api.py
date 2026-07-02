"""API gateway integration tests (§14). Uses a temp Kuzu store (auto-seeded)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):  # type: ignore[no-untyped-def]
    # point the store at a temp dir and reset the cached singleton
    import api_gateway.deps as deps

    from kg_common.config import get_settings

    d = tmp_path_factory.mktemp("kuzu")
    get_settings().kuzu_db_path = str(Path(d) / "g")
    deps.get_store.cache_clear()

    from api_gateway.main import app

    return TestClient(app)


def test_health(client: TestClient) -> None:
    assert client.get("/api/v1/admin/health").json()["status"] == "ok"


def test_metrics_records_routes(client: TestClient) -> None:
    client.get("/api/v1/admin/health")
    m = client.get("/api/v1/admin/metrics").json()
    assert "routes" in m and any("count" in v for v in m["routes"].values())


def test_graph_schema(client: TestClient) -> None:
    r = client.get("/api/v1/graph/schema").json()
    assert len(r["labels"]) >= 33
    assert any(x["rel"] == "OF_PROPERTY" for x in r["relationships"])


def test_query_deterministic(client: TestClient) -> None:
    r = client.post(
        "/api/v1/query",
        json={
            "query": "методы обессоливания воды сульфаты 200–300 мг/л TDS ≤1000 мг/дм³",
            "use_llm": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answerMarkdown"]
    assert body["graph"]["nodes"]
    assert "parsedQuery" in body


def test_entity_search(client: TestClient) -> None:
    r = client.get("/api/v1/entities/search", params={"q": "осмос"}).json()
    assert r["count"] >= 1


def test_glossary(client: TestClient) -> None:
    r = client.get("/api/v1/domain/glossary", params={"q": "электроэкстракция"}).json()
    assert r["count"] >= 1


def test_coverage(client: TestClient) -> None:
    r = client.get("/api/v1/admin/coverage").json()
    assert any(d["domain"] == "water_treatment" for d in r["domains"])


def test_export_markdown(client: TestClient) -> None:
    r = client.post(
        "/api/v1/export",
        json={
            "query": "обессоливание воды обратный осмос",
            "format": "markdown",
            "use_llm": False,
        },
    )
    assert r.status_code == 200 and "Отчёт" in r.text


def test_gaps_and_contradictions(client: TestClient) -> None:
    assert client.get("/api/v1/gaps").json()["count"] >= 1
    assert client.get("/api/v1/contradictions").json()["count"] >= 1


def test_gap_scan(client: TestClient) -> None:
    res = client.post("/api/v1/gaps/scan").json()
    assert "gaps" in res and "contradictions" in res and "run_id" in res


def test_curation_edit_and_history(client: TestClient) -> None:
    r = client.post(
        "/api/v1/entities/material:nickel/edit",
        json={"changes": {"name": "Никель (эксперт)"}, "reason": "уточнение"},
        headers={"x-user": "expert2"},
    )
    assert r.status_code == 200
    hist = client.get("/api/v1/entities/material:nickel/history").json()["history"]
    assert hist and hist[0]["actor"] == "expert2"


def test_curation_queue(client: TestClient) -> None:
    q = client.get("/api/v1/curation/queue").json()["items"]
    assert isinstance(q, list)


def test_auth_login_and_role(client: TestClient) -> None:
    tok = client.post("/api/v1/auth/login", json={"username": "vasil", "role": "analyst"}).json()[
        "token"
    ]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["role"] == "analyst" and me["user"] == "vasil"


def test_rbac_via_jwt(client: TestClient) -> None:
    q = "циркуляция католита электроэкстракция никеля"
    partner_tok = client.post(
        "/api/v1/auth/login", json={"username": "ext", "role": "external_partner"}
    ).json()["token"]
    researcher = client.post("/api/v1/query", json={"query": q, "use_llm": False}).json()
    partner = client.post(
        "/api/v1/query",
        json={"query": q, "use_llm": False},
        headers={"Authorization": f"Bearer {partner_tok}"},
    ).json()
    assert len(partner["citations"]) <= len(researcher["citations"])


def test_comparison_cells_evidence_or_gap(client: TestClient) -> None:
    r = client.post(
        "/api/v1/comparison",
        json={"query": "методы обессоливания воды обратный осмос ионный обмен"},
    ).json()
    assert r["columns"] and r["rows"]
    # §24.13: every metric cell is either evidence-backed or explicitly a gap
    for row in r["rows"]:
        for _col, cell in row.items():
            if isinstance(cell, dict):
                assert cell.get("gap") is True or "evidence_ids" in cell


def test_notifications_subscribe_and_fetch(client: TestClient) -> None:
    tok = client.post(
        "/api/v1/auth/login", json={"username": "subuser", "role": "researcher"}
    ).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    client.post(
        "/api/v1/notifications/subscribe",
        json={"topic": "циркуляция католита электроэкстракция никеля"},
        headers=h,
    )
    subs = client.get("/api/v1/notifications/subscriptions", headers=h).json()["subscriptions"]
    assert subs
    notifs = client.get("/api/v1/notifications", headers=h).json()["notifications"]
    # the seed has a catholyte-velocity contradiction → at least one notification
    assert any("противоречие" in n["summary"] for n in notifs)


def test_audit_log_records(client: TestClient) -> None:
    admin_tok = client.post(
        "/api/v1/auth/login", json={"username": "boss", "role": "admin"}
    ).json()["token"]
    client.post("/api/v1/query", json={"query": "тест аудита", "use_llm": False})
    entries = client.get(
        "/api/v1/admin/audit", headers={"Authorization": f"Bearer {admin_tok}"}
    ).json()["entries"]
    assert any(e["action"] == "query" for e in entries)
