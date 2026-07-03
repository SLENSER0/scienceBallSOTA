"""Tests for the ``/admin/health`` readiness/liveness rollup (§14.11)."""

from __future__ import annotations

from api_gateway.health_rollup import HealthRollup, roll_up


def test_all_up_is_ok() -> None:
    """Все зависимости живы → status 'ok', http_code 200."""
    rollup = roll_up({"neo4j": True, "qdrant": True}, critical={"neo4j"})
    assert rollup.status == "ok"
    assert rollup.http_code == 200
    assert rollup.checks == {"neo4j": "ok", "qdrant": "ok"}


def test_critical_down_is_down_503() -> None:
    """Падение критичной зависимости → status 'down', http_code 503."""
    rollup = roll_up({"neo4j": False, "qdrant": True}, critical={"neo4j"})
    assert rollup.status == "down"
    assert rollup.http_code == 503


def test_optional_down_is_degraded_200() -> None:
    """Падение только опциональной зависимости → 'degraded', http_code 200."""
    rollup = roll_up({"neo4j": True, "qdrant": False}, critical={"neo4j"})
    assert rollup.status == "degraded"
    assert rollup.http_code == 200


def test_failing_name_reflected_in_checks() -> None:
    """checks['neo4j'] == 'down' отражает конкретное имя упавшей проверки."""
    rollup = roll_up({"neo4j": False, "qdrant": True}, critical={"neo4j"})
    assert rollup.checks["neo4j"] == "down"
    assert rollup.checks["qdrant"] == "ok"


def test_empty_checks_is_ok() -> None:
    """Пустой набор проверок → 'ok' (нечему падать)."""
    rollup = roll_up({}, critical={"neo4j"})
    assert rollup.status == "ok"
    assert rollup.http_code == 200
    assert rollup.checks == {}


def test_as_dict_has_expected_keys() -> None:
    """as_dict() содержит ключи status/checks/http_code."""
    rollup = roll_up({"neo4j": True}, critical={"neo4j"})
    data = rollup.as_dict()
    assert set(data) == {"status", "checks", "http_code"}
    assert data["status"] == "ok"
    assert data["checks"] == {"neo4j": "ok"}
    assert data["http_code"] == 200


def test_critical_down_dominates_over_optionals() -> None:
    """Упавшая критичная зависимость доминирует даже если опциональные тоже упали."""
    rollup = roll_up(
        {"neo4j": False, "qdrant": False, "bm25": False},
        critical={"neo4j"},
    )
    assert rollup.status == "down"
    assert rollup.http_code == 503
    assert rollup.checks == {"neo4j": "down", "qdrant": "down", "bm25": "down"}


def test_rollup_is_frozen() -> None:
    """HealthRollup — frozen dataclass (неизменяемый результат)."""
    rollup = HealthRollup(status="ok", checks={"neo4j": "ok"}, http_code=200)
    try:
        rollup.status = "down"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("HealthRollup must be immutable (frozen)")
