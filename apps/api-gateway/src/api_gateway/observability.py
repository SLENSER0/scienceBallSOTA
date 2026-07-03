"""Lightweight request metrics + latency middleware (§18).

In-process counters/latency per route + a request_id bound into structlog. For a
full deployment these export to OpenTelemetry/Prometheus (see kg_common.telemetry).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from kg_common import get_logger

_log = get_logger("api.obs")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, round((pct / 100.0) * (len(s) - 1)))
    return round(s[k], 1)


class Metrics:
    def __init__(self) -> None:
        self.count: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.latency_ms_sum: dict[str, float] = defaultdict(float)
        # bounded window of recent latencies per route for percentile estimates
        self.latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=256))

    def record(self, route: str, ms: float, *, error: bool) -> None:
        self.count[route] += 1
        self.latency_ms_sum[route] += ms
        self.latencies[route].append(ms)
        if error:
            self.errors[route] += 1

    def snapshot(self) -> dict:
        out = {}
        for route, n in self.count.items():
            recent = list(self.latencies[route])
            out[route] = {
                "count": n,
                "errors": self.errors.get(route, 0),
                "avg_ms": round(self.latency_ms_sum[route] / n, 1) if n else 0.0,
                "p50_ms": _percentile(recent, 50),
                "p95_ms": _percentile(recent, 95),
            }
        return out


METRICS = Metrics()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        # honor an inbound request id + W3C traceparent so the trace is continuous
        # across services (§18.2); create a child span for this gateway hop.
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        from kg_common.tracing import child_context, new_span_id, parse_traceparent, root_context

        parent = parse_traceparent(request.headers.get("traceparent", ""))
        ctx = child_context(parent, new_span_id()) if parent else root_context()
        structlog.contextvars.bind_contextvars(request_id=rid, trace_id=ctx.trace_id)
        route = f"{request.method} {request.url.path}"
        t0 = time.perf_counter()
        error = False
        try:
            response = await call_next(request)
            error = response.status_code >= 500
            response.headers["X-Request-ID"] = rid  # propagate downstream + to client
            response.headers["traceparent"] = ctx.to_header()
            return response
        except Exception:
            error = True
            raise
        finally:
            ms = (time.perf_counter() - t0) * 1000
            METRICS.record(route, ms, error=error)
            structlog.contextvars.unbind_contextvars("request_id")
