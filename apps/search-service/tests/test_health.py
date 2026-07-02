"""Smoke test for search-service."""

from __future__ import annotations

from search_service.main import create_app


def test_create_app() -> None:
    svc = create_app()
    assert svc.health()["status"] == "ok"
