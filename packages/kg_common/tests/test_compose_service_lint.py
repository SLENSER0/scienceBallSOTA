"""Tests for the compose service lint (health/restart/limits/logs) (§2.5)."""

from __future__ import annotations

from kg_common.compose_service_lint import (
    ServiceLintFinding,
    is_stateful,
    lint_services,
)

# A fully-specified service that trips none of the four rules.
_FULL_SERVICE: dict[str, object] = {
    "healthcheck": {"test": ["CMD", "true"], "interval": "30s"},
    "restart": "unless-stopped",
    "deploy": {"resources": {"limits": {"cpus": "1.0", "memory": "512M"}}},
    "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
}


def _rules(services: dict[str, dict[str, object]]) -> set[str]:
    """Collect the rule codes emitted for a single-service mapping."""
    return {f.rule for f in lint_services(services)}


def test_bare_service_yields_all_four_rules() -> None:
    """A service with none of the keys trips every rule exactly once."""
    findings = lint_services({"web": {}})
    assert {f.rule for f in findings} == {
        "SL_NO_HEALTHCHECK",
        "SL_NO_RESTART",
        "SL_NO_LIMITS",
        "SL_NO_LOG_ROTATION",
    }
    assert len(findings) == 4
    assert all(f.service == "web" for f in findings)


def test_healthcheck_present_omits_rule() -> None:
    """A ``healthcheck`` dict suppresses SL_NO_HEALTHCHECK only."""
    rules = _rules({"web": {"healthcheck": {"test": ["CMD", "true"]}}})
    assert "SL_NO_HEALTHCHECK" not in rules
    assert "SL_NO_RESTART" in rules


def test_restart_present_omits_rule() -> None:
    """``restart: unless-stopped`` suppresses SL_NO_RESTART only."""
    rules = _rules({"web": {"restart": "unless-stopped"}})
    assert "SL_NO_RESTART" not in rules
    assert "SL_NO_HEALTHCHECK" in rules


def test_limits_present_omits_rule() -> None:
    """A populated ``deploy.resources.limits`` suppresses SL_NO_LIMITS only."""
    service = {"deploy": {"resources": {"limits": {"memory": "256M"}}}}
    rules = _rules({"web": service})
    assert "SL_NO_LIMITS" not in rules
    assert "SL_NO_HEALTHCHECK" in rules


def test_log_rotation_present_omits_rule() -> None:
    """``logging.options.max-size`` suppresses SL_NO_LOG_ROTATION only."""
    service = {"logging": {"options": {"max-size": "10m"}}}
    rules = _rules({"web": service})
    assert "SL_NO_LOG_ROTATION" not in rules
    assert "SL_NO_HEALTHCHECK" in rules


def test_deploy_without_resources_still_flags_limits() -> None:
    """A ``deploy`` block missing ``resources`` does not satisfy the limits rule."""
    assert "SL_NO_LIMITS" in _rules({"web": {"deploy": {"replicas": 2}}})


def test_resources_without_limits_still_flags() -> None:
    """``deploy.resources`` present but empty ``limits`` still trips SL_NO_LIMITS."""
    service = {"deploy": {"resources": {"reservations": {"memory": "64M"}}}}
    assert "SL_NO_LIMITS" in _rules({"web": service})


def test_logging_without_options_still_flags() -> None:
    """``logging`` with a driver but no ``options`` still trips SL_NO_LOG_ROTATION."""
    assert "SL_NO_LOG_ROTATION" in _rules({"web": {"logging": {"driver": "json-file"}}})


def test_fully_specified_service_yields_no_findings() -> None:
    """A service declaring all four safety nets produces zero findings."""
    assert lint_services({"neo4j": _FULL_SERVICE}) == ()


def test_findings_sorted_service_then_rule() -> None:
    """Findings across two services are sorted by (service, rule)."""
    findings = lint_services({"zeta": {}, "alpha": {}})
    keys = [(f.service, f.rule) for f in findings]
    assert keys == sorted(keys)
    # 'alpha' block precedes 'zeta' block entirely.
    services_in_order = [f.service for f in findings]
    assert services_in_order == ["alpha"] * 4 + ["zeta"] * 4
    # Within 'alpha', rules are alphabetical.
    alpha_rules = [f.rule for f in findings if f.service == "alpha"]
    assert alpha_rules == sorted(alpha_rules)


def test_every_rule_code_has_sl_prefix() -> None:
    """Each finding.as_dict()['rule'] starts with 'SL_'."""
    findings = lint_services({"web": {}, "db": {}})
    assert findings  # non-empty
    assert all(f.as_dict()["rule"].startswith("SL_") for f in findings)


def test_as_dict_full_shape() -> None:
    """``as_dict()`` exposes service, rule and message keys."""
    finding = lint_services({"web": {}})[0]
    d = finding.as_dict()
    assert set(d) == {"service", "rule", "message"}
    assert d["service"] == "web"
    assert isinstance(d["message"], str) and d["message"]


def test_finding_is_frozen() -> None:
    """The finding dataclass is immutable — frozen guarantees stable outputs."""
    finding = ServiceLintFinding(service="web", rule="SL_NO_RESTART", message="x")
    try:
        finding.rule = "SL_OTHER"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen must raise
        raise AssertionError("ServiceLintFinding should be frozen")


def test_empty_services_yields_no_findings() -> None:
    """An empty service mapping produces an empty tuple."""
    assert lint_services({}) == ()


def test_is_stateful_known_storage() -> None:
    """Known storage services are flagged stateful, case-insensitively."""
    assert is_stateful("neo4j") is True
    assert is_stateful("Qdrant") is True
    assert is_stateful("postgres") is True


def test_is_stateful_unknown_service() -> None:
    """An app/web service is not stateful."""
    assert is_stateful("web") is False
    assert is_stateful("api-gateway") is False


def test_is_stateful_replica_suffix_and_prefix() -> None:
    """A replica index and a compose project prefix still resolve to storage."""
    assert is_stateful("neo4j-1") is True
    assert is_stateful("proj_neo4j") is True


def test_partial_service_flags_only_missing_nets() -> None:
    """A service with healthcheck+restart only trips limits and log rotation."""
    service = {
        "healthcheck": {"test": ["CMD", "true"]},
        "restart": "always",
    }
    assert _rules({"web": service}) == {"SL_NO_LIMITS", "SL_NO_LOG_ROTATION"}


def test_return_type_is_tuple() -> None:
    """``lint_services`` returns a tuple, not a list."""
    assert isinstance(lint_services({"web": {}}), tuple)
