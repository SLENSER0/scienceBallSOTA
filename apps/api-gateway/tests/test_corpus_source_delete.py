"""Tests for DELETE /api/v1/corpus/sources/{doc_id} — destructive source purge (§5).

Proves the role-gated endpoint (a) as an admin purges the source node together with
every derived node (matched by ``doc_id``) while leaving shared canonical entities
untouched, (b) forbids a role without the ``delete`` capability with 403 and touches
nothing, and (c) is idempotent — deleting a missing id is a 200 with ``deleted_nodes=0``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import api_gateway.routers.corpus_source_delete as csd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kg_retrievers.graph_store import KuzuGraphStore

_SRC = "Paper:src1"


def _seed_store() -> KuzuGraphStore:
    """A source :Paper + derived nodes (doc_id=source) plus a shared canonical entity."""
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    store.upsert_node(_SRC, "Paper", name="Источник 1")
    # Derived nodes carry the source's node id in their queryable doc_id column (§1).
    store.upsert_node("Chunk:c1", "Chunk", name="chunk-1", doc_id=_SRC, text="никель ...")
    store.upsert_node("Measurement:m1", "Measurement", name="m-1", doc_id=_SRC)
    store.upsert_node("Evidence:e1", "Evidence", name="e-1", doc_id=_SRC)
    # Shared canonical entity: NO doc_id and a different id → MUST survive the cascade.
    store.upsert_node("Material:nickel", "Material", name="никель")
    store.upsert_edge(_SRC, "Chunk:c1", "HAS_CHUNK")
    store.upsert_edge("Chunk:c1", "Material:nickel", "MENTIONS")
    return store


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(csd.router)
    return TestClient(app)


def test_admin_deletes_source_and_derived(monkeypatch) -> None:
    store = _seed_store()
    monkeypatch.setattr(csd, "get_store", lambda: store)
    try:
        r = _client().delete(f"/api/v1/corpus/sources/{_SRC}", headers={"X-Role": "admin"})
        assert r.status_code == 200
        body = r.json()
        assert body["source_id"] == _SRC
        assert body["deleted_nodes"] >= 4  # source + 3 derived (Chunk/Measurement/Evidence)
        # No registry/vector wired on the embedded profile → both purges are no-ops.
        assert body["registry_deleted"] is False
        assert body["vector_purged"] is False
        # Source + derived gone; the shared canonical entity is untouched.
        assert store.get_node(_SRC) is None
        assert store.get_node("Chunk:c1") is None
        assert store.get_node("Measurement:m1") is None
        assert store.get_node("Evidence:e1") is None
        assert store.get_node("Material:nickel") is not None
    finally:
        store.close()


def test_unprivileged_role_forbidden(monkeypatch) -> None:
    store = _seed_store()
    monkeypatch.setattr(csd, "get_store", lambda: store)
    try:
        r = _client().delete(f"/api/v1/corpus/sources/{_SRC}", headers={"X-Role": "researcher"})
        assert r.status_code == 403
        # A role without the "delete" capability changes nothing.
        assert store.get_node(_SRC) is not None
        assert store.get_node("Chunk:c1") is not None
    finally:
        store.close()


def test_missing_source_is_idempotent(monkeypatch) -> None:
    store = _seed_store()
    monkeypatch.setattr(csd, "get_store", lambda: store)
    try:
        r = _client().delete(
            "/api/v1/corpus/sources/Paper:does-not-exist", headers={"X-Role": "admin"}
        )
        assert r.status_code == 200
        assert r.json()["deleted_nodes"] == 0
        # The real source is left intact by an unrelated idempotent delete.
        assert store.get_node(_SRC) is not None
    finally:
        store.close()
