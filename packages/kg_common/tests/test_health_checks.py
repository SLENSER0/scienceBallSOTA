"""Health-check tests (§13.1/§14.11) — run against the LIVE server-profile stack.

Each network test first opens a raw TCP socket to decide reachability; it asserts a
real ``ok=True`` when the container answers and ``pytest.skip``s only when the port
is genuinely closed. No randomness — nothing here needs a namespace token, and the
probes are read-only (they create no state to clean up).
"""

from __future__ import annotations

import socket
from dataclasses import FrozenInstanceError

import pytest

from kg_common.config import Settings
from kg_common.health_checks import (
    HealthStatus,
    aggregate_health,
    check_neo4j,
    check_opensearch,
    check_postgres,
    check_qdrant,
    check_redis,
)


def _tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """True if a TCP connection to ``host:port`` succeeds within ``timeout``."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _require(host: str, port: int) -> None:
    if not _tcp_open(host, port):
        pytest.skip(f"{host}:{port} not reachable — dependency down")


@pytest.fixture
def settings() -> Settings:
    return Settings()


# --------------------------------------------------------------------------- #
# HealthStatus dataclass
# --------------------------------------------------------------------------- #
def test_healthstatus_as_dict_shape() -> None:
    st = HealthStatus(name="demo", ok=True, detail="up", latency_ms=1.5)
    d = st.as_dict()
    assert d == {"name": "demo", "ok": True, "detail": "up", "latency_ms": 1.5}
    assert set(d) == {"name", "ok", "detail", "latency_ms"}
    assert isinstance(d["ok"], bool) and isinstance(d["latency_ms"], float)


def test_healthstatus_is_frozen() -> None:
    st = HealthStatus(name="demo", ok=True, detail="up", latency_ms=1.5)
    with pytest.raises(FrozenInstanceError):
        st.ok = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Live probes — assert ok=True when the container is reachable
# --------------------------------------------------------------------------- #
def test_check_qdrant_live(settings: Settings) -> None:
    host, port = "localhost", 6333
    _require(host, port)
    st = check_qdrant(settings.qdrant_url)
    assert st.name == "qdrant"
    assert st.ok is True, st.detail
    assert st.latency_ms >= 0.0


def test_check_opensearch_live(settings: Settings) -> None:
    _require("localhost", 9200)
    st = check_opensearch(settings.opensearch_url)
    assert st.name == "opensearch"
    assert st.ok is True, st.detail
    assert st.latency_ms >= 0.0


def test_check_neo4j_live(settings: Settings) -> None:
    _require("localhost", 7687)
    st = check_neo4j(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    assert st.name == "neo4j"
    assert st.ok is True, st.detail
    assert st.latency_ms >= 0.0


def test_check_postgres_live(settings: Settings) -> None:
    _require("localhost", 5432)
    st = check_postgres(settings.postgres_dsn)
    assert st.name == "postgres"
    assert st.ok is True, st.detail


def test_check_redis_live(settings: Settings) -> None:
    _require("localhost", 6379)
    st = check_redis(settings.redis_url)
    assert st.name == "redis"
    assert st.ok is True, st.detail


# --------------------------------------------------------------------------- #
# Failure path — a bogus target must return ok=False and NEVER raise
# --------------------------------------------------------------------------- #
def test_bogus_target_never_raises() -> None:
    # Port 1 is reserved/closed — every probe should fail fast without raising.
    q = check_qdrant("http://localhost:1", timeout=1.0)
    r = check_redis("redis://localhost:1/0", timeout=1.0)
    n = check_neo4j("bolt://localhost:1", "neo4j", "password", timeout=1.0)
    p = check_postgres("postgresql://kg:kg@localhost:1/kg_app", timeout=1.0)
    for st in (q, r, n, p):
        assert st.ok is False, st.detail
        assert isinstance(st.detail, str) and st.detail
        assert st.latency_ms >= 0.0


# --------------------------------------------------------------------------- #
# Aggregate
# --------------------------------------------------------------------------- #
def test_aggregate_health_ok_when_core_up(settings: Settings) -> None:
    for host, port in (
        ("localhost", 7687),
        ("localhost", 6333),
        ("localhost", 9200),
        ("localhost", 5432),
        ("localhost", 6379),
    ):
        _require(host, port)
    report = aggregate_health(settings)
    assert report["status"] == "ok", report
    checks = report["checks"]
    assert isinstance(checks, list) and len(checks) == 5
    names = {c["name"] for c in checks}
    assert names == {"neo4j", "qdrant", "opensearch", "postgres", "redis"}
    assert all(c["ok"] is True for c in checks)


def test_aggregate_health_down_when_all_unreachable() -> None:
    # Point every dependency at a closed port — status must fold to "down".
    dead = Settings(
        NEO4J_URI="bolt://localhost:1",
        QDRANT_URL="http://localhost:1",
        OPENSEARCH_URL="http://localhost:1",
        POSTGRES_DSN="postgresql://kg:kg@localhost:1/kg_app",
        REDIS_URL="redis://localhost:1/0",
    )
    report = aggregate_health(dead, timeout=1.0)
    assert report["status"] == "down", report
    assert all(c["ok"] is False for c in report["checks"])
