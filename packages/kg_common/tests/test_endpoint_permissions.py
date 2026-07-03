"""Tests for endpoint -> permission fail-closed coverage (§19.1 authz coverage)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.security.endpoint_permissions import (
    ENDPOINT_RULES,
    PUBLIC_ROUTES,
    CoverageReport,
    EndpointRule,
    audit_coverage,
    required_permission,
)


def test_required_permission_known_mutate_route_returns_scope() -> None:
    # (1) a known mutate route resolves to its scope.
    assert required_permission("POST", "/documents") == "documents:upload"


def test_required_permission_public_route_returns_none() -> None:
    # (2) a PUBLIC_ROUTES path resolves to None.
    assert required_permission("GET", "/health") is None


def test_required_permission_unknown_route_is_keyerror_free() -> None:
    # Unknown route returns None (no KeyError) at lookup level.
    assert required_permission("PATCH", "/nope") is None


def test_unknown_route_appears_in_unmapped() -> None:
    # (3) an unknown route is a fail-closed violation.
    report = audit_coverage([("PATCH", "/secret/backdoor")])
    assert ("PATCH", "/secret/backdoor") in report.unmapped
    assert report.mapped == ()
    assert report.public == ()


def test_public_route_appears_in_public_section() -> None:
    # (4) a public route lands in report.public.
    report = audit_coverage([("GET", "/health")])
    assert ("GET", "/health") in report.public
    assert report.unmapped == ()


def test_mapped_route_appears_in_mapped_with_scope() -> None:
    report = audit_coverage([("POST", "/documents")])
    assert report.mapped == (EndpointRule("POST", "/documents", "documents:upload"),)
    assert report.public == ()
    assert report.unmapped == ()


def test_fully_covered_routes_have_empty_unmapped() -> None:
    # (5) when every route is covered, unmapped == ().
    routes = [(r.method, r.path) for r in ENDPOINT_RULES]
    routes += [("GET", p) for p in sorted(PUBLIC_ROUTES)]
    report = audit_coverage(routes)
    assert report.unmapped == ()
    assert len(report.mapped) == len(ENDPOINT_RULES)
    assert len(report.public) == len(PUBLIC_ROUTES)


def test_endpoint_rule_as_dict_has_expected_keys() -> None:
    # (6) EndpointRule.as_dict exposes method/path/permission.
    rule = EndpointRule("POST", "/documents", "documents:upload")
    assert rule.as_dict() == {
        "method": "POST",
        "path": "/documents",
        "permission": "documents:upload",
    }


def test_audit_coverage_ordering_is_deterministic() -> None:
    # (7) sections preserve first-seen input order.
    routes = [
        ("POST", "/documents"),  # mapped
        ("GET", "/health"),  # public
        ("PATCH", "/zzz"),  # unmapped
        ("GET", "/documents"),  # mapped
        ("GET", "/readyz"),  # public
        ("PATCH", "/aaa"),  # unmapped
    ]
    report = audit_coverage(routes)
    assert [(r.method, r.path) for r in report.mapped] == [
        ("POST", "/documents"),
        ("GET", "/documents"),
    ]
    assert report.public == (("GET", "/health"), ("GET", "/readyz"))
    assert report.unmapped == (("PATCH", "/zzz"), ("PATCH", "/aaa"))


def test_audit_coverage_deduplicates_repeated_routes() -> None:
    report = audit_coverage(
        [("POST", "/documents"), ("POST", "/documents"), ("PATCH", "/x"), ("PATCH", "/x")]
    )
    assert len(report.mapped) == 1
    assert len(report.unmapped) == 1


def test_audit_coverage_empty_input() -> None:
    report = audit_coverage([])
    assert report == CoverageReport((), (), ())


def test_coverage_report_as_dict_shape() -> None:
    report = audit_coverage([("POST", "/documents"), ("GET", "/health"), ("PATCH", "/x")])
    assert report.as_dict() == {
        "mapped": [{"method": "POST", "path": "/documents", "permission": "documents:upload"}],
        "public": [["GET", "/health"]],
        "unmapped": [["PATCH", "/x"]],
    }


def test_public_routes_and_rules_do_not_overlap() -> None:
    # A path cannot be both mapped and public — public wins, so guard the table.
    rule_paths = {r.path for r in ENDPOINT_RULES}
    assert rule_paths.isdisjoint(PUBLIC_ROUTES)


def test_dataclasses_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        EndpointRule("POST", "/x", "s").method = "GET"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        CoverageReport((), (), ()).mapped = ()  # type: ignore[misc]
