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
