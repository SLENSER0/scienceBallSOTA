"""Tests for the corpus topic-map endpoint (GET /api/v1/cluster-map)."""

from __future__ import annotations

import json

from api_gateway.routers import cluster_map
from fastapi import FastAPI
from fastapi.testclient import TestClient

_FAKE = {
    "points": [{"x": 0.1, "y": 0.2, "z": 0.3, "c": 0, "t": "секретный текст чанка"}],
    "clusters": [
        {"id": 0, "label": "флотация", "terms": ["флотация", "реагент"], "size": 10, "pct": 100.0}
    ],
    "total": 10,
    "shown": 1,
    "var3d": 26.8,
    "k": 12,
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(cluster_map.router)
    return TestClient(app)


def _use_file(tmp_path, monkeypatch, data=_FAKE):
    p = tmp_path / "cluster_map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(cluster_map, "_path", lambda: p)
    cluster_map._cache["mtime"] = None
    cluster_map._cache["data"] = None
    return p


def test_full_role_sees_chunk_text(tmp_path, monkeypatch) -> None:
    _use_file(tmp_path, monkeypatch)
    r = _client().get("/api/v1/cluster-map", headers={"X-Role": "researcher"})
    assert r.status_code == 200
    d = r.json()
    assert d["cached"] is True
    assert d["points"][0]["t"] == "секретный текст чанка"
    assert "text_redacted" not in d


def test_restricted_role_text_redacted(tmp_path, monkeypatch) -> None:
    _use_file(tmp_path, monkeypatch)
    r = _client().get("/api/v1/cluster-map", headers={"X-Role": "external_partner"})
    assert r.status_code == 200
    d = r.json()
    assert d["text_redacted"] is True
    assert "t" not in d["points"][0]  # raw chunk text withheld
    assert d["points"][0]["c"] == 0 and "x" in d["points"][0]  # coords/labels stay
    assert d["clusters"][0]["label"] == "флотация"


def test_refresh_ignored_for_restricted_role(tmp_path, monkeypatch) -> None:
    _use_file(tmp_path, monkeypatch)
    calls = {"n": 0}
    monkeypatch.setattr(cluster_map, "_build", lambda: (calls.update(n=calls["n"] + 1) or _FAKE))
    r = _client().get("/api/v1/cluster-map?refresh=true", headers={"X-Role": "external_partner"})
    assert r.status_code == 200
    assert r.json()["cached"] is True
    assert calls["n"] == 0  # a restricted role cannot trigger the heavy rebuild


def test_refresh_allowed_for_full_role(tmp_path, monkeypatch) -> None:
    _use_file(tmp_path, monkeypatch)
    calls = {"n": 0}

    def fake_build() -> dict:
        calls["n"] += 1
        return {**_FAKE, "total": 99}

    monkeypatch.setattr(cluster_map, "_build", fake_build)
    r = _client().get("/api/v1/cluster-map?refresh=true", headers={"X-Role": "curator"})
    assert r.status_code == 200
    assert r.json()["total"] == 99
    assert calls["n"] == 1


def test_build_error_is_graceful_not_500(tmp_path, monkeypatch) -> None:
    p = tmp_path / "cluster_map.json"  # missing → forces a build
    monkeypatch.setattr(cluster_map, "_path", lambda: p)
    cluster_map._cache["mtime"] = None
    cluster_map._cache["data"] = None
    import kg_retrievers.corpus_topic_map as ctm

    def boom(**kw):
        raise RuntimeError("degenerate corpus")

    monkeypatch.setattr(ctm, "fetch_and_build", boom)
    r = _client().get("/api/v1/cluster-map", headers={"X-Role": "researcher"})
    assert r.status_code == 200  # not a 500
    assert r.json()["total"] == 0
