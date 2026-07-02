"""API Gateway (FastAPI) — public HTTP surface (§6.2 / §14).

Health/metrics live here from the start; feature routers (query, graph, search,
evidence, export, domain, admin, auth) are mounted as they are built.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kg_common import configure, get_logger, get_settings, setup_observability

_log = get_logger("api-gateway")
_STARTED = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure("api-gateway")
    setup_observability("api-gateway")
    get_settings().ensure_runtime_dirs()
    _log.info("api-gateway.startup")
    yield
    _log.info("api-gateway.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Научный клубок — API Gateway",
        version="0.1.0",
        description="R&D knowledge-graph API for mining & metallurgy.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    from api_gateway.observability import ObservabilityMiddleware

    app.add_middleware(ObservabilityMiddleware)

    @app.get("/api/v1/admin/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "api-gateway",
            "uptime_s": round(time.time() - _STARTED, 1),
        }

    @app.get("/api/v1/admin/metrics")
    def metrics() -> dict[str, Any]:
        from api_gateway.observability import METRICS

        s = get_settings()
        return {
            "service": "api-gateway",
            "runtime_profile": s.runtime_profile,
            "uptime_s": round(time.time() - _STARTED, 1),
            "models": {"extract": s.llm_model_extract, "synth": s.llm_model_synth},
            "routes": METRICS.snapshot(),
        }

    # Feature routers are attached here as subsystems come online.
    try:
        from api_gateway.routers import attach_routers

        attach_routers(app)
    except Exception as exc:  # routers optional until built
        _log.warning("api-gateway.routers_unavailable", error=str(exc))

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("api_gateway.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
