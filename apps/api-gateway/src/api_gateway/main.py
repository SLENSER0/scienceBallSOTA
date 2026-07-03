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


def _prometheus(snapshot: dict) -> str:
    """Render the route metrics snapshot as Prometheus text exposition (§14.11)."""

    def esc(v: str) -> str:
        return v.replace("\\", "\\\\").replace('"', '\\"')

    lines = [
        "# TYPE http_requests_total counter",
        "# TYPE http_request_errors_total counter",
        "# TYPE http_request_latency_ms gauge",
    ]
    for route, m in snapshot.items():
        lbl = f'route="{esc(route)}"'
        lines.append(f"http_requests_total{{{lbl}}} {m['count']}")
        lines.append(f"http_request_errors_total{{{lbl}}} {m['errors']}")
        lines.append(f'http_request_latency_ms{{{lbl},quantile="0.5"}} {m.get("p50_ms", 0.0)}')
        lines.append(f'http_request_latency_ms{{{lbl},quantile="0.95"}} {m.get("p95_ms", 0.0)}')
    return "\n".join(lines) + "\n"


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure("api-gateway")
    setup_observability("api-gateway")
    settings = get_settings()
    settings.ensure_runtime_dirs()
    settings.require_prod_secret()  # fail-fast on placeholder JWT secret outside local
    settings.validate_required()  # fail-fast on a misconfigured server profile (§2.2)
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

    # Structured error taxonomy (§14.2): map KgError + generic exceptions to a
    # uniform ErrorResponse, carrying the request id and redacting secrets (§19.7).
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from kg_common.errors import KgError, http_status_for, to_error_response
    from kg_common.security.redaction import redact

    @app.exception_handler(KgError)
    def _kg_error_handler(request: Request, exc: KgError) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        body = to_error_response(exc, request_id=rid).model_dump(by_alias=True)
        body["message"] = redact(str(body.get("message", "")))
        return JSONResponse(body, status_code=http_status_for(exc))

    from fastapi.exceptions import RequestValidationError

    from kg_common.errors import ErrorResponse

    @app.exception_handler(RequestValidationError)
    def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        body = ErrorResponse(
            error_code="validation_error",
            message="request validation failed",
            detail={"errors": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]},
            request_id=rid,
        ).model_dump(by_alias=True)
        return JSONResponse(body, status_code=422)

    @app.exception_handler(Exception)
    def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # never leak an internal stack trace to the client (§14.2)
        rid = request.headers.get("X-Request-ID")
        _log.error("unhandled", error=redact(str(exc))[:200], path=request.url.path)
        body = ErrorResponse(
            error_code="internal_error", message="internal server error", request_id=rid
        ).model_dump(by_alias=True)
        return JSONResponse(body, status_code=500)

    @app.get("/api/v1/admin/health")
    def health() -> Any:
        # Aggregated readiness: 503 if a critical dependency (the graph) is down,
        # 'degraded' if a non-critical one is, else 'ok' (§14.11).
        from fastapi.responses import JSONResponse

        from api_gateway.deps import get_store

        checks: dict[str, str] = {}
        try:
            get_store().rows("MATCH (n:Node) RETURN count(n) LIMIT 1")
            checks["graph"] = "ok"
        except Exception as e:
            checks["graph"] = f"error: {type(e).__name__}"
        status = "ok" if checks["graph"] == "ok" else "down"
        body = {
            "status": status,
            "service": "api-gateway",
            "uptime_s": round(time.time() - _STARTED, 1),
            "checks": checks,
        }
        return JSONResponse(body, status_code=200 if status == "ok" else 503)

    @app.get("/api/v1/admin/metrics")
    def metrics(format: str = "json") -> Any:  # query param name intentionally 'format'
        from fastapi.responses import PlainTextResponse

        from api_gateway.observability import METRICS

        s = get_settings()
        snap = METRICS.snapshot()
        if format == "prometheus":
            return PlainTextResponse(_prometheus(snap), media_type="text/plain; version=0.0.4")
        return {
            "service": "api-gateway",
            "runtime_profile": s.runtime_profile,
            "uptime_s": round(time.time() - _STARTED, 1),
            "models": {"extract": s.llm_model_extract, "synth": s.llm_model_synth},
            "routes": snap,
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
