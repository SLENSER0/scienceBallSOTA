"""Health-route smoke test (§1.4)."""

from __future__ import annotations

from agent_service.main import app
from fastapi.testclient import TestClient


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
