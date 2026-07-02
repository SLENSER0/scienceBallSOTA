"""Smoke test for curation-service."""

from __future__ import annotations

from curation_service.main import create_app


def test_create_app() -> None:
    svc = create_app()
    assert svc.health()["status"] == "ok"
