"""Lightweight request metrics + latency middleware (§18).

In-process counters/latency per route + a request_id bound into structlog. For a
full deployment these export to OpenTelemetry/Prometheus (see kg_common.telemetry).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from kg_common import get_logger

_log = get_logger("api.obs")


class Metrics:
    def __init__(self) -> None:
        self.count: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.latency_ms_sum: dict[str, float] = defaultdict(float)

    def record(self, route: str, ms: float, *, error: bool) -> None:
        self.count[route] += 1
        self.latency_ms_sum[route] += ms
        if error:
            self.errors[route] += 1

    def snapshot(self) -> dict:
        out = {}
        for route, n in self.count.items():
            out[route] = {
                "count": n,
                "errors": self.errors.get(route, 0),
                "avg_ms": round(self.latency_ms_sum[route] / n, 1) if n else 0.0,
            }
        return out


METRICS = Metrics()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = uuid.uuid4().hex[:12]
        structlog.contextvars.bind_contextvars(request_id=rid)
        route = f"{request.method} {request.url.path}"
        t0 = time.perf_counter()
        error = False
        try:
            response = await call_next(request)
            error = response.status_code >= 500
            return response
        except Exception:
            error = True
            raise
        finally:
            ms = (time.perf_counter() - t0) * 1000
            METRICS.record(route, ms, error=error)
            structlog.contextvars.unbind_contextvars("request_id")
