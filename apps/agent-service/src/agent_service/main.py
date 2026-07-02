"""Научный клубок — Agent Service (FastAPI) — health endpoint (§1.4 / §13.1)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from kg_common import configure, get_logger, setup_observability

_log = get_logger("agent-service")


def create_app() -> FastAPI:
    configure("agent-service")
    setup_observability("agent-service")
    app = FastAPI(title="Научный клубок — Agent Service", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "agent-service"}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("agent_service.main:app", host="0.0.0.0", port=8010, reload=False)


if __name__ == "__main__":
    run()
