#!/usr/bin/env python3
"""Generate minimal-but-real skeletons for the remaining backend apps.

FastAPI apps (agent-service:8010, ingestion-service:8020) get a health endpoint.
Worker/library services (graph/search/extraction/curation) get a ``create_app``
placeholder that real modules will grow into. Idempotent for files that already
carry real logic (only writes the two named FastAPI mains + lib stubs + tests
when missing / still a scaffold).
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

FASTAPI_MAIN = '''\
"""{title} (FastAPI) — health endpoint (§1.4 / §13.1)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from kg_common import configure, get_logger, setup_observability

_log = get_logger("{svc}")


def create_app() -> FastAPI:
    configure("{svc}")
    setup_observability("{svc}")
    app = FastAPI(title="{title}", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {{"status": "ok", "service": "{svc}"}}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("{pkg}.main:app", host="0.0.0.0", port={port}, reload=False)  # noqa: S104


if __name__ == "__main__":
    run()
'''

LIB_MAIN = '''\
"""{title} — worker/library service (§6.1).

No public HTTP port at this stage; exposes a service factory used by other apps
and by the orchestration pipeline.
"""

from __future__ import annotations

from kg_common import get_logger

_log = get_logger("{svc}")


class {cls}:
    """Placeholder service object; concrete logic lives in sibling modules."""

    name = "{svc}"

    def health(self) -> dict[str, str]:
        return {{"status": "ok", "service": self.name}}


def create_app() -> {cls}:
    return {cls}()
'''

HEALTH_TEST_FASTAPI = '''\
"""Health-route smoke test (§1.4)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from {pkg}.main import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("{path}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
'''

HEALTH_TEST_LIB = '''\
"""Smoke test for {svc}."""

from __future__ import annotations

from {pkg}.main import create_app


def test_create_app() -> None:
    svc = create_app()
    assert svc.health()["status"] == "ok"
'''

FASTAPI = {
    "agent-service": ("agent_service", "Научный клубок — Agent Service", 8010),
    "ingestion-service": ("ingestion_service", "Научный клубок — Ingestion Service", 8020),
}
LIBS = {
    "graph-service": ("graph_service", "Graph Service", "GraphService"),
    "search-service": ("search_service", "Search Service", "SearchService"),
    "extraction-service": ("extraction_service", "Extraction Service", "ExtractionService"),
    "curation-service": ("curation_service", "Curation Service", "CurationService"),
}


def _write_if_scaffold(path: pathlib.Path, content: str) -> None:
    if (
        path.exists()
        and "def create_app" in path.read_text(encoding="utf-8")
        and "placeholder" not in path.read_text(encoding="utf-8")
    ):
        return  # real logic already present
    path.write_text(content, encoding="utf-8")


def main() -> None:
    for svc, (pkg, title, port) in FASTAPI.items():
        main_py = ROOT / "apps" / svc / "src" / pkg / "main.py"
        if not main_py.exists():
            main_py.write_text(
                FASTAPI_MAIN.format(svc=svc, title=title, port=port, pkg=pkg), encoding="utf-8"
            )
        test_py = ROOT / "apps" / svc / "tests" / "test_health.py"
        test_py.write_text(HEALTH_TEST_FASTAPI.format(pkg=pkg, path="/health"), encoding="utf-8")

    for svc, (pkg, title, cls) in LIBS.items():
        main_py = ROOT / "apps" / svc / "src" / pkg / "main.py"
        _write_if_scaffold(main_py, LIB_MAIN.format(svc=svc, title=title, cls=cls))
        test_py = ROOT / "apps" / svc / "tests" / "test_health.py"
        test_py.write_text(HEALTH_TEST_LIB.format(svc=svc, pkg=pkg), encoding="utf-8")

    # api-gateway health test (main.py hand-written separately)
    (ROOT / "apps" / "api-gateway" / "tests" / "test_health.py").write_text(
        HEALTH_TEST_FASTAPI.format(pkg="api_gateway", path="/api/v1/admin/health"), encoding="utf-8"
    )
    print("app skeletons generated")


if __name__ == "__main__":
    main()
