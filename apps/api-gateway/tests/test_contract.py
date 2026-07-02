"""API contract guard (§23.2): the OpenAPI surface must not silently break.

A frozen set of critical (method, path) pairs and response DTO schemas must
remain present in the generated OpenAPI — removing/renaming one fails CI, acting
as a lightweight breaking-change detector without external tooling.
"""

from __future__ import annotations

import pytest

CRITICAL_PATHS = {
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/query"),
    ("get", "/api/v1/graph/schema"),
    ("post", "/api/v1/graph/subgraph"),
    ("get", "/api/v1/evidence/{evidence_id}"),
    ("post", "/api/v1/gaps/scan"),
    ("get", "/api/v1/gaps"),
    ("get", "/api/v1/entities/search"),
    ("post", "/api/v1/entities/{entity_id}/status"),
    ("get", "/api/v1/entities/{entity_id}/history"),
    ("post", "/api/v1/comparison"),
    ("get", "/api/v1/admin/audit"),
    ("get", "/api/v1/admin/health"),
}

CRITICAL_SCHEMAS = {"GraphResponse", "GraphNode", "GraphEdge"}


@pytest.fixture(scope="module")
def spec() -> dict:
    from api_gateway.main import app

    return app.openapi()


def test_critical_paths_present(spec: dict) -> None:
    have = {
        (method, path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method in {"get", "post", "put", "delete"}
    }
    missing = CRITICAL_PATHS - have
    assert not missing, f"contract regression — missing endpoints: {sorted(missing)}"


def test_critical_schemas_present(spec: dict) -> None:
    schemas = set(spec.get("components", {}).get("schemas", {}))
    missing = CRITICAL_SCHEMAS - schemas
    assert not missing, f"contract regression — missing DTO schemas: {sorted(missing)}"


def test_openapi_is_versioned(spec: dict) -> None:
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["version"]
