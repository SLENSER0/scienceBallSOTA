"""Научный клубок — Ingestion Service (FastAPI) — health endpoint (§1.4 / §13.1)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from kg_common import configure, get_logger, setup_observability

_log = get_logger("ingestion-service")


def create_app() -> FastAPI:
    configure("ingestion-service")
    setup_observability("ingestion-service")
    app = FastAPI(title="Научный клубок — Ingestion Service", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "ingestion-service"}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("ingestion_service.main:app", host="0.0.0.0", port=8020, reload=False)


if __name__ == "__main__":
    run()
