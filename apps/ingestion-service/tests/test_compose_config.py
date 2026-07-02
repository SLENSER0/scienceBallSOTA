"""Server-profile docker-compose is structurally valid (§2/§13.1).

Verifiable without a Docker daemon: the compose file parses, declares every
expected service, each service has a healthcheck, app services wait on their
dependencies' health, and every named volume is declared.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE = Path(__file__).resolve().parents[3] / "infra" / "docker-compose.yml"

EXPECTED_SERVICES = {
    "neo4j",
    "qdrant",
    "opensearch",
    "postgres",
    "redis",
    "minio",
    "docling-serve",
    "api-gateway",
    "agent-service",
    "ingestion-service",
    "frontend",
}


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_all_expected_services_present(compose: dict) -> None:
    assert set(compose["services"]) == EXPECTED_SERVICES


def test_every_service_has_a_healthcheck(compose: dict) -> None:
    missing = [s for s, v in compose["services"].items() if "healthcheck" not in v]
    assert not missing, f"services without healthcheck: {missing}"


def test_healthchecks_have_a_test_command(compose: dict) -> None:
    for name, svc in compose["services"].items():
        hc = svc["healthcheck"]
        assert hc.get("test"), f"{name} healthcheck missing test"
        assert hc.get("retries"), f"{name} healthcheck missing retries"


def test_app_services_wait_for_dependency_health(compose: dict) -> None:
    for app in ("api-gateway", "ingestion-service", "agent-service", "frontend"):
        deps = compose["services"][app].get("depends_on", {})
        assert deps, f"{app} declares no dependencies"
        assert all(
            d.get("condition") == "service_healthy" for d in deps.values()
        ), f"{app} must gate on dependency health"


def test_all_referenced_volumes_declared(compose: dict) -> None:
    declared = set(compose.get("volumes", {}))
    for svc in compose["services"].values():
        for vol in svc.get("volumes", []):
            src = vol.split(":", 1)[0]
            if src and not src.startswith((".", "/")):  # named volume, not bind mount
                assert src in declared, f"undeclared volume {src!r}"
