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


def _auth(client: TestClient, role: str) -> dict[str, str]:
    tok = client.post("/api/v1/auth/login", json={"username": role, "role": role}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


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


def test_lineage(client: TestClient) -> None:
    runs = client.get("/api/v1/admin/lineage").json()["runs"]
    # the seed's ExtractorRun should appear
    assert any(r["type"] == "ExtractorRun" for r in runs)


def test_communities(client: TestClient) -> None:
    res = client.post("/api/v1/admin/communities").json()
    assert res["communities"] >= 1 and res["nodes_assigned"] >= 4


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


def test_search_keyword_and_hybrid(client: TestClient) -> None:
    r = client.get("/api/v1/search/keyword", params={"q": "осмос вода"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "keyword"
    assert all("score" in x for x in body["results"])
    h = client.get("/api/v1/search/hybrid", params={"q": "осмос"}).json()
    assert h["mode"] == "hybrid"
    # hybrid results are score-sorted desc
    scores = [x["score"] for x in h["results"]]
    assert scores == sorted(scores, reverse=True)


def test_search_vector_degrades_without_index(client: TestClient) -> None:
    v = client.get("/api/v1/search/vector", params={"q": "никель"}).json()
    assert v["mode"] == "vector"
    # no prebuilt entity index in the test store → graceful keyword fallback
    assert v.get("degraded") is True


def test_community_global_and_local_search(client: TestClient) -> None:
    client.post("/api/v1/admin/communities")  # detect first
    g = client.get("/api/v1/admin/communities/global-search", params={"q": "осмос вода"}).json()
    assert "answer" in g and "communities" in g
    loc = client.get(
        "/api/v1/admin/communities/local-search",
        params={"seed": "reverse osmosis desalination"},
    ).json()
    assert "neighbors" in loc


def test_graph_nodes_and_path(client: TestClient) -> None:
    r = client.get("/api/v1/graph/nodes", params={"label": "TechnologySolution", "limit": 5}).json()
    assert r["count"] >= 1 and all(n["type"] == "TechnologySolution" for n in r["nodes"])
    # path between two connected seed nodes
    ns = client.get("/api/v1/graph/nodes", params={"domain": "water_treatment", "limit": 20}).json()
    ids = [n["id"] for n in ns["nodes"]]
    if len(ids) >= 2:
        p = client.get("/api/v1/graph/path", params={"source": ids[0], "target": ids[0]}).json()
        assert p["found"] and p["hops"] == 0
    # missing node → not found
    miss = client.get("/api/v1/graph/path", params={"source": "nope", "target": "nada"}).json()
    assert miss["found"] is False


def test_gaps_detail_matrix_and_filter(client: TestClient) -> None:
    client.post("/api/v1/gaps/scan")
    gaps = client.get("/api/v1/gaps").json()["gaps"]
    assert gaps
    gid = gaps[0]["id"]
    d = client.get(f"/api/v1/gaps/{gid}").json()
    assert d["id"] == gid and "about" in d
    # matrix view
    m = client.get("/api/v1/gaps/matrix").json()
    assert m["matrix"]
    # filter by type returns only that type
    gt = gaps[0]["type"]
    filt = client.get("/api/v1/gaps", params={"gap_type": gt}).json()["gaps"]
    assert all(g["type"] == gt for g in filt)
    # unknown gap → 404
    assert client.get("/api/v1/gaps/nope").status_code == 404


def test_post_search_unified_hits_filters_and_422(client: TestClient) -> None:
    r = client.post("/api/v1/search/hybrid", json={"query": "осмос", "top_k": 5})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert hits and all(
        {"id", "text", "score", "doc_id", "page", "metadata"} <= set(h) for h in hits
    )
    # invalid top_k → 422
    assert client.post("/api/v1/search/keyword", json={"query": "x", "top_k": 0}).status_code == 422
    # verified_only filter narrows (seed entities are mostly unverified)
    all_hits = client.post("/api/v1/search/keyword", json={"query": "вода", "top_k": 50}).json()[
        "count"
    ]
    v = client.post(
        "/api/v1/search/keyword",
        json={"query": "вода", "top_k": 50, "filters": {"verified_only": True}},
    ).json()["count"]
    assert v <= all_hits


def test_evidence_by_node_and_review(client: TestClient) -> None:
    import api_gateway.deps as deps

    # insert a fact backed by an evidence span
    store = deps.get_store()
    store.upsert_node("meas:evtest", "Measurement", name="твёрдость", value_normalized=145.0)
    store.upsert_node("ev:evtest", "Evidence", text="145 HV после старения", doc_id="doc:x", page=3)
    store.upsert_edge("meas:evtest", "ev:evtest", "SUPPORTED_BY")

    by = client.get("/api/v1/evidence/by-node/meas:evtest").json()
    assert by["count"] == 1 and by["evidence"][0]["evidence_id"] == "ev:evtest"

    # curator review flips the evidence status
    rv = client.post(
        "/api/v1/evidence/ev:evtest/review",
        json={"status": "accepted"},
        headers=_auth(client, "curator"),
    )
    assert rv.status_code == 200 and rv.json()["review_status"] == "accepted"
    assert client.get("/api/v1/evidence/ev:evtest").json()["review_status"] == "accepted"

    # researcher may not review (RBAC)
    forbidden = client.post(
        "/api/v1/evidence/ev:evtest/review",
        json={"status": "rejected"},
        headers=_auth(client, "researcher"),
    )
    assert forbidden.status_code == 403


def test_request_id_propagation(client: TestClient) -> None:
    # a generated request id is echoed on the response
    r = client.get("/api/v1/admin/health")
    assert r.headers.get("X-Request-ID")
    # an inbound request id is honored (continuous trace, §18.2)
    r2 = client.get("/api/v1/admin/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r2.headers.get("X-Request-ID") == "trace-abc-123"


def test_metrics_has_latency_percentiles(client: TestClient) -> None:
    for _ in range(3):
        client.get("/api/v1/admin/health")
    m = client.get("/api/v1/admin/metrics").json()["routes"]
    row = next(v for v in m.values() if v["count"] >= 1)
    assert "p50_ms" in row and "p95_ms" in row and row["p95_ms"] >= 0.0


def test_graphrag_global_search_and_status(client: TestClient) -> None:
    client.post("/api/v1/admin/communities")  # build the index
    st = client.get("/api/v1/graphrag/status").json()
    assert st["active"] is True and st["build_version"].startswith("cg-")
    g = client.post("/api/v1/search/global", json={"query": "осмос ионный обмен вода"}).json()
    assert "answer" in g and "used_community_ids" in g and "sources" in g
    assert g["used_community_ids"]  # ≥1 relevant community on seed


def test_readiness_probe(client: TestClient) -> None:
    r = client.get("/api/v1/admin/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True and body["checks"]["graph"] == "ok"


def test_entity_detail_and_search_ordering(client: TestClient) -> None:
    # /entities/search must still resolve (not shadowed by /entities/{id})
    assert client.get("/api/v1/entities/search", params={"q": "осмос"}).json()["count"] >= 1
    d = client.get("/api/v1/entities/material:nickel").json()
    assert d["id"] == "material:nickel" and d["type"] == "Material"
    assert "evidence_count" in d and "neighbor_count" in d
    assert client.get("/api/v1/entities/no:such").status_code == 404


def test_export_subgraph_jsonld(client: TestClient) -> None:
    # §24.19: exported subgraph has JSON-LD @context + stable @id per node/edge
    r = client.post(
        "/api/v1/export/subgraph",
        json={"node_ids": ["material:nickel", "tech:catholyte-circulation-scheme"], "expand": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert "@context" in body and body["@type"] == "kg:KnowledgeSubgraph"
    assert body["dcterms:license"] == "CC-BY-4.0"  # FAIR reusable
    assert body["@graph"], "subgraph must contain nodes/edges"
    assert all(item["@id"].startswith("kg:") for item in body["@graph"])  # stable ids


def test_health_aggregated_and_prometheus_metrics(client: TestClient) -> None:
    h = client.get("/api/v1/admin/health").json()
    assert h["status"] == "ok" and h["checks"]["graph"] == "ok"  # aggregated readiness
    prom = client.get("/api/v1/admin/metrics", params={"format": "prometheus"})
    assert prom.status_code == 200 and "text/plain" in prom.headers["content-type"]
    assert "http_requests_total{" in prom.text and "quantile=\"0.95\"" in prom.text


def test_admin_absence_map_and_coverage_matrix(client: TestClient) -> None:
    am = client.get("/api/v1/admin/absence-map").json()
    assert "summary" in am or "cells" in am or "by_status" in am
    cm = client.get("/api/v1/admin/coverage-matrix").json()
    assert "matrix" in cm and "by_owner" in cm and "timeline" in cm


def test_admin_validate_shapes(client: TestClient) -> None:
    r = client.get("/api/v1/admin/validate-shapes").json()
    assert "conforms" in r and "total" in r and "by_severity" in r
    assert r["total"] >= 1


def test_admin_retrieval_eval(client: TestClient) -> None:
    r = client.get("/api/v1/admin/retrieval-eval").json()
    assert "aggregate" in r and "per_query" in r


def test_error_taxonomy_wired(client: TestClient) -> None:
    from kg_common.errors import (
        KgError,
        NotFoundError,
        http_status_for,
        to_error_response,
    )

    assert http_status_for(NotFoundError("x")) == 404
    d = to_error_response(NotFoundError("no such node"), request_id="r1").model_dump(by_alias=True)
    assert d["errorCode"] == "not_found" and d["requestId"] == "r1"
    # the KgError handler is registered on the app
    from api_gateway.main import create_app

    assert KgError in create_app().exception_handlers


def test_audit_redacts_secrets(client: TestClient) -> None:
    from api_gateway import audit

    audit.record("test", user="u", role="admin", detail={"token": "sk-abcdef1234567890", "q": "ok"})
    entries = audit.tail(5)
    rec = next(e for e in entries if e["action"] == "test")
    assert rec["detail"]["q"] == "ok"
    assert "sk-abcdef1234567890" not in str(rec["detail"])  # secret masked
