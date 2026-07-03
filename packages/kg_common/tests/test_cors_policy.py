"""Tests for the CORS allowlist resolver (§19.7 secrets/transport hardening)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.security.cors_policy import CorsDecision, CorsPolicy, resolve_cors


def test_listed_origin_is_echoed_and_allowed() -> None:
    policy = CorsPolicy(frozenset({"https://a.io"}))
    decision = resolve_cors(policy, "https://a.io")
    assert decision.allowed is True
    assert decision.headers["Access-Control-Allow-Origin"] == "https://a.io"


def test_unlisted_origin_is_denied_with_no_headers() -> None:
    policy = CorsPolicy(frozenset({"https://a.io"}))
    decision = resolve_cors(policy, "https://evil.io")
    assert decision.allowed is False
    assert decision.headers == {}


def test_credentialed_policy_emits_credentials_header() -> None:
    policy = CorsPolicy(frozenset({"https://a.io"}), allow_credentials=True)
    decision = resolve_cors(policy, "https://a.io")
    assert decision.headers["Access-Control-Allow-Credentials"] == "true"
    # Concrete origin echoed, never '*', when credentials are allowed.
    assert decision.headers["Access-Control-Allow-Origin"] == "https://a.io"


def test_wildcard_with_credentials_is_rejected_fail_closed() -> None:
    with pytest.raises(ValueError):
        CorsPolicy(frozenset({"*"}), allow_credentials=True)


def test_wildcard_non_credentialed_answers_star() -> None:
    policy = CorsPolicy(frozenset({"*"}))
    decision = resolve_cors(policy, "https://x.io")
    assert decision.allowed is True
    assert decision.headers["Access-Control-Allow-Origin"] == "*"


def test_wildcard_decision_carries_max_age_and_methods() -> None:
    policy = CorsPolicy(frozenset({"*"}))
    decision = resolve_cors(policy, "https://x.io")
    assert decision.headers["Access-Control-Max-Age"] == "600"
    assert "GET" in decision.headers["Access-Control-Allow-Methods"]


def test_wildcard_response_has_no_vary_origin() -> None:
    # A '*' answer is origin-independent, so no Vary: Origin is needed.
    policy = CorsPolicy(frozenset({"*"}))
    decision = resolve_cors(policy, "https://x.io")
    assert "Vary" not in decision.headers


def test_listed_origin_response_varies_on_origin() -> None:
    policy = CorsPolicy(frozenset({"https://a.io"}))
    decision = resolve_cors(policy, "https://a.io")
    assert decision.headers["Vary"] == "Origin"


def test_custom_max_age_and_headers_are_reflected() -> None:
    policy = CorsPolicy(
        frozenset({"https://a.io"}),
        allowed_headers=("X-Trace",),
        max_age=42,
    )
    decision = resolve_cors(policy, "https://a.io")
    assert decision.headers["Access-Control-Max-Age"] == "42"
    assert decision.headers["Access-Control-Allow-Headers"] == "X-Trace"


def test_policy_is_frozen() -> None:
    policy = CorsPolicy(frozenset({"https://a.io"}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.max_age = 1  # type: ignore[misc]


def test_policy_as_dict_roundtrips_fields() -> None:
    policy = CorsPolicy(frozenset({"https://a.io"}), allow_credentials=True)
    data = policy.as_dict()
    assert data["allowed_origins"] == ["https://a.io"]
    assert data["allow_credentials"] is True
    assert data["max_age"] == 600
    assert "GET" in data["allowed_methods"]


def test_decision_as_dict_is_json_friendly() -> None:
    decision = resolve_cors(CorsPolicy(frozenset({"https://a.io"})), "https://a.io")
    data = decision.as_dict()
    assert data["allowed"] is True
    assert data["headers"]["Access-Control-Allow-Origin"] == "https://a.io"
    # Returned headers are a copy, not the live decision mapping.
    data["headers"]["injected"] = "x"
    assert "injected" not in decision.headers


def test_denied_decision_as_dict() -> None:
    decision = CorsDecision(allowed=False)
    assert decision.as_dict() == {"allowed": False, "headers": {}}
