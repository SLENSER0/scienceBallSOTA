"""Tests for the corpus topic-map endpoint (GET /api/v1/cluster-map)."""

from __future__ import annotations

import json

from api_gateway.routers import cluster_map
from fastapi import FastAPI
from fastapi.testclient import TestClient

_FAKE = {
    "points": [{"x": 0.1, "y": 0.2, "z": 0.3, "c": 0, "t": "чанк текста"}],
    "clusters": [
        {"id": 0, "label": "флотация", "terms": ["флотация", "реагент"], "size": 10, "pct": 100.0}
    ],
    "total": 10,
    "shown": 1,
    "var3d": 26.8,
    "k": 1,
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(cluster_map.router)
    return TestClient(app)


def _reset_cache() -> None:
    cluster_map._cache["mtime"] = None
    cluster_map._cache["data"] = None


def test_serves_cached_file(tmp_path, monkeypatch) -> None:
    p = tmp_path / "cluster_map.json"
    p.write_text(json.dumps(_FAKE), encoding="utf-8")
    monkeypatch.setattr(cluster_map, "_path", lambda: p)
    _reset_cache()
    r = _client().get("/api/v1/cluster-map")
    assert r.status_code == 200
    d = r.json()
    assert d["cached"] is True
    assert d["total"] == 10
    assert len(d["clusters"]) == 1
    assert d["clusters"][0]["label"] == "флотация"
    assert set(d["points"][0]) == {"x", "y", "z", "c", "t"}


def test_builds_when_file_missing(tmp_path, monkeypatch) -> None:
    p = tmp_path / "cluster_map.json"  # does not exist
    monkeypatch.setattr(cluster_map, "_path", lambda: p)
    monkeypatch.setattr(cluster_map, "_build", lambda k: {**_FAKE, "k": k})  # no real Qdrant
    _reset_cache()
    r = _client().get("/api/v1/cluster-map")
    assert r.status_code == 200
    d = r.json()
    assert d["cached"] is False
    assert d["total"] == 10


def test_refresh_forces_rebuild(tmp_path, monkeypatch) -> None:
    p = tmp_path / "cluster_map.json"
    p.write_text(json.dumps(_FAKE), encoding="utf-8")
    monkeypatch.setattr(cluster_map, "_path", lambda: p)
    calls = {"n": 0}

    def fake_build(k: int) -> dict:
        calls["n"] += 1
        return {**_FAKE, "total": 99}

    monkeypatch.setattr(cluster_map, "_build", fake_build)
    _reset_cache()
    r = _client().get("/api/v1/cluster-map?refresh=true")
    assert r.status_code == 200
    assert r.json()["total"] == 99
    assert calls["n"] == 1  # refresh bypassed the cache and rebuilt
