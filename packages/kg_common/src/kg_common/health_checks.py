"""Dependency health checks — проверки живости внешних зависимостей (§13.1/§14.11).

The *server* runtime profile (Neo4j / Qdrant / OpenSearch / Postgres / Redis) runs
against real network services. Deployment tooling, readiness endpoints and the
``/health`` route (§14.11) need a cheap, uniform way to ask *"is each dependency
alive right now?"* without dragging in heavy client libraries or ever crashing the
caller. Каждая проверка — дешёвый liveness-probe с коротким таймаутом.

Design rules:

* **Никогда не бросает.** Every ``check_*`` returns a :class:`HealthStatus`; any
  failure (refused socket, timeout, auth error, missing driver) is captured as
  ``ok=False`` with a human-readable ``detail`` — the probe itself never raises.
* **Pure-python first, optional clients second.** HTTP services are probed with the
  stdlib (:mod:`urllib`); Redis / Postgres via raw sockets speaking one line of
  their wire protocol. Neo4j uses its official driver when importable, otherwise a
  plain TCP liveness on the bolt port. No probe requires a package that is not
  already installed.
* **Short timeout.** Every probe is bounded by ``timeout`` seconds so a dead host
  fails fast instead of hanging a health endpoint.

Public API:

* :class:`HealthStatus`  — frozen ``{name, ok, detail, latency_ms}`` + ``as_dict``.
* :func:`check_neo4j`, :func:`check_qdrant`, :func:`check_opensearch`,
  :func:`check_postgres`, :func:`check_redis` — one dependency each.
* :func:`aggregate_health` — probe every server-profile dependency, fold into
  ``{status: ok|degraded|down, checks: [...]}``.
"""

from __future__ import annotations

import contextlib
import socket
import struct
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from kg_common.config import Settings

try:  # optional client — official Neo4j driver (bolt)
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - driver optional
    GraphDatabase = None  # type: ignore[assignment]

try:  # optional client — redis-py
    import redis as _redis
except ImportError:  # pragma: no cover - client optional
    _redis = None  # type: ignore[assignment]

__all__ = [
    "HealthStatus",
    "aggregate_health",
    "check_neo4j",
    "check_opensearch",
    "check_postgres",
    "check_qdrant",
    "check_redis",
]

_DEFAULT_TIMEOUT = 2.0
# Postgres SSLRequest packet: length=8, request code 80877103 (1234 << 16 | 5679).
_PG_SSL_REQUEST = struct.pack("!ii", 8, 80877103)


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Immutable result of one dependency probe — итог одной проверки."""

    name: str
    ok: bool
    detail: str
    latency_ms: float

    def as_dict(self) -> dict[str, object]:
        """Plain JSON-serializable mapping for API responses / logs."""
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
        }


def _elapsed_ms(t0: float) -> float:
    """Milliseconds since ``t0`` (a :func:`time.perf_counter` reading)."""
    return round((time.perf_counter() - t0) * 1000.0, 3)


def _parse_hostport(url: str, default_port: int) -> tuple[str, int]:
    """Extract ``(host, port)`` from a URL/DSN, filling in a default port."""
    parsed = urlparse(url if "//" in url else f"//{url}")
    return (parsed.hostname or "localhost"), (parsed.port or default_port)


def _http_liveness(name: str, url: str, timeout: float) -> HealthStatus:
    """GET the service root; treat a 2xx/3xx response as alive."""
    t0 = time.perf_counter()
    target = url.rstrip("/") + "/"
    try:
        req = urllib.request.Request(target, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = int(resp.status)
        return HealthStatus(name, 200 <= code < 400, f"GET {target} -> {code}", _elapsed_ms(t0))
    except urllib.error.HTTPError as exc:  # server responded, but with an error status
        return HealthStatus(name, False, f"GET {target} -> HTTP {exc.code}", _elapsed_ms(t0))
    except Exception as exc:  # URLError / timeout / DNS — never raise
        return HealthStatus(name, False, f"{type(exc).__name__}: {exc}", _elapsed_ms(t0))


def _tcp_liveness(name: str, url: str, default_port: int, timeout: float) -> HealthStatus:
    """Fallback probe: can we open a TCP connection to ``host:port``?"""
    t0 = time.perf_counter()
    host, port = _parse_hostport(url, default_port)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return HealthStatus(name, True, f"tcp {host}:{port} open", _elapsed_ms(t0))
    except Exception as exc:
        return HealthStatus(name, False, f"{type(exc).__name__}: {exc}", _elapsed_ms(t0))


def check_neo4j(
    uri: str, user: str, pw: object, *, timeout: float = _DEFAULT_TIMEOUT
) -> HealthStatus:
    """Probe Neo4j with ``RETURN 1``; ``pw`` may be a str or a ``SecretStr``."""
    name = "neo4j"
    if GraphDatabase is None:  # no driver installed — degrade to a bolt TCP probe
        return _tcp_liveness(name, uri, 7687, timeout)
    t0 = time.perf_counter()
    password = pw.get_secret_value() if hasattr(pw, "get_secret_value") else str(pw)
    driver = None
    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=timeout,
            connection_acquisition_timeout=timeout,
            max_transaction_retry_time=0.0,
        )
        with driver.session() as session:
            value = session.run("RETURN 1 AS ok").single()["ok"]
        return HealthStatus(name, value == 1, f"RETURN 1 -> {value}", _elapsed_ms(t0))
    except Exception as exc:
        return HealthStatus(name, False, f"{type(exc).__name__}: {exc}", _elapsed_ms(t0))
    finally:
        if driver is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - best-effort cleanup
                driver.close()


def check_qdrant(url: str, *, timeout: float = _DEFAULT_TIMEOUT) -> HealthStatus:
    """Probe Qdrant via ``GET /`` (returns build info with 200)."""
    return _http_liveness("qdrant", url, timeout)


def check_opensearch(url: str, *, timeout: float = _DEFAULT_TIMEOUT) -> HealthStatus:
    """Probe OpenSearch via ``GET /`` (returns cluster info with 200)."""
    return _http_liveness("opensearch", url, timeout)


def check_redis(url: str, *, timeout: float = _DEFAULT_TIMEOUT) -> HealthStatus:
    """Probe Redis with ``PING`` — via redis-py if present, else a raw socket."""
    name = "redis"
    t0 = time.perf_counter()
    if _redis is not None:  # optional client path
        client = None
        try:
            client = _redis.from_url(url, socket_timeout=timeout, socket_connect_timeout=timeout)
            pong = client.ping()
            return HealthStatus(name, bool(pong), f"PING -> {pong}", _elapsed_ms(t0))
        except Exception as exc:
            return HealthStatus(name, False, f"{type(exc).__name__}: {exc}", _elapsed_ms(t0))
        finally:
            if client is not None:
                with contextlib.suppress(Exception):  # pragma: no cover - best-effort cleanup
                    client.close()
    # Pure-python inline command: send "PING\r\n", expect "+PONG".
    host, port = _parse_hostport(url, 6379)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"PING\r\n")
            reply = sock.recv(64)
        ok = reply.startswith(b"+PONG")
        detail = "PING -> " + repr(reply.decode("latin1").strip())
        return HealthStatus(name, ok, detail, _elapsed_ms(t0))
    except Exception as exc:
        return HealthStatus(name, False, f"{type(exc).__name__}: {exc}", _elapsed_ms(t0))


def check_postgres(dsn: str, *, timeout: float = _DEFAULT_TIMEOUT) -> HealthStatus:
    """Probe Postgres liveness with an ``SSLRequest`` wire handshake.

    A full ``SELECT 1`` needs a DBAPI driver and credentials; without one we send
    the driver-free ``SSLRequest`` startup packet — a live server always answers
    with a single byte (``S`` = TLS available, ``N`` = plaintext), which proves it
    is accepting connections. Проверяет живость без пароля и без драйвера.
    """
    name = "postgres"
    t0 = time.perf_counter()
    host, port = _parse_hostport(dsn, 5432)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_PG_SSL_REQUEST)
            reply = sock.recv(1)
        ok = reply in (b"S", b"N")
        return HealthStatus(name, ok, f"SSLRequest -> {reply!r}", _elapsed_ms(t0))
    except Exception as exc:
        return HealthStatus(name, False, f"{type(exc).__name__}: {exc}", _elapsed_ms(t0))


def aggregate_health(settings: Settings, *, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, object]:
    """Probe every server-profile dependency and fold into a single verdict.

    Returns ``{"status": "ok"|"degraded"|"down", "checks": [<as_dict>, ...]}`` where
    ``status`` is ``ok`` when all probes pass, ``down`` when none do, and
    ``degraded`` in between — so a readiness endpoint can 200 / 503 accordingly.
    """
    checks = [
        check_neo4j(
            settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, timeout=timeout
        ),
        check_qdrant(settings.qdrant_url, timeout=timeout),
        check_opensearch(settings.opensearch_url, timeout=timeout),
        check_postgres(settings.postgres_dsn, timeout=timeout),
        check_redis(settings.redis_url, timeout=timeout),
    ]
    ok_n = sum(1 for c in checks if c.ok)
    if ok_n == len(checks):
        status = "ok"
    elif ok_n == 0:
        status = "down"
    else:
        status = "degraded"
    return {"status": status, "checks": [c.as_dict() for c in checks]}
