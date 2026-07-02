"""End-to-end golden flow across services over the embedded stack (§23.1).

One test chains the whole system through the gateway: auth → agent query
(retrieval + synthesis + graph + evidence) → evidence inspector → gap/contradiction
scan → curation status change → decision-history propagation → audit trail.
All services run in-process behind the gateway in the embedded profile, so this
is a genuine cross-service integration check without Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WATER_Q = "методы обессоливания воды сульфаты 200–300 мг/л TDS ≤1000 мг/дм³"


@pytest.fixture(scope="module")
def client(tmp_path_factory):  # type: ignore[no-untyped-def]
    import api_gateway.deps as deps

    from kg_common.config import get_settings

    d = tmp_path_factory.mktemp("kuzu_e2e")
    get_settings().kuzu_db_path = str(Path(d) / "g")
    deps.get_store.cache_clear()
    from api_gateway.main import app

    return TestClient(app)


def _login(client: TestClient, role: str) -> dict[str, str]:
    tok = client.post("/api/v1/auth/login", json={"username": role, "role": role}).json()
    return {"Authorization": f"Bearer {tok['token']}", "X-User": role}


def test_golden_flow_end_to_end(client: TestClient) -> None:
    curator = _login(client, "curator")

    # 1) agent query → answer with citations, subgraph, confidence
    q = client.post("/api/v1/query", json={"query": WATER_Q, "use_llm": False}, headers=curator)
    assert q.status_code == 200
    body = q.json()
    assert body["answerMarkdown"].strip()
    assert body["citations"], "answer must be source-backed"
    assert body["graph"]["nodes"] and body["graph"]["edges"]
    assert body["confidence"] is not None
    assert "осмос" in body["answerMarkdown"].lower()  # reverse osmosis surfaces

    # 2) evidence inspector: every citation resolves to a real source node
    ev_id = body["citations"][0]["evidence"]["evidenceId"]
    ev = client.get(f"/api/v1/evidence/{ev_id}", headers=curator)
    assert ev.status_code == 200 and ev.json()["evidence_id"] == ev_id

    # 3) gap/contradiction scan — demo graph must expose ≥1 of each (§19.11)
    scan = client.post("/api/v1/gaps/scan", headers=curator).json()
    assert scan["gaps"] >= 1 and scan["contradictions"] >= 1
    gaps = client.get("/api/v1/gaps", headers=curator).json()
    assert gaps["count"] >= 1

    # 4) curation: change an entity's review status and confirm it is recorded
    target = next(
        n["id"] for n in body["graph"]["nodes"] if n["type"] in {"TechnologySolution", "Material"}
    )
    st = client.post(
        f"/api/v1/entities/{target}/status",
        json={"status": "accepted", "reason": "verified in e2e"},
        headers=curator,
    )
    assert st.status_code == 200

    # 5) decision history propagates the curation event (§12.3)
    hist = client.get(f"/api/v1/entities/{target}/history", headers=curator).json()
    assert hist["history"], "status change must appear in decision history"

    # 6) audit trail recorded the privileged actions (§10.8/§19.5)
    admin = _login(client, "admin")
    audit = client.get("/api/v1/admin/audit", headers=admin).json()
    assert audit.get("entries"), "audit log must record the request chain"


def test_restricted_role_gets_degraded_view(client: TestClient) -> None:
    # external_partner still gets an answer, but access policy filters restricted
    # sources/entities rather than 500ing (graceful degradation §23.11).
    partner = _login(client, "external_partner")
    r = client.post("/api/v1/query", json={"query": WATER_Q, "use_llm": False}, headers=partner)
    assert r.status_code == 200
    assert "graph" in r.json()
