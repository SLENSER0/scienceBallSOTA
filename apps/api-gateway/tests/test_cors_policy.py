"""Tests for the §14.12 CORS allowlist policy / preflight header building.

Проверяет allowlist источников и сборку preflight-заголовков: точное
совпадение origin, wildcard ``*``, отклонение чужих origin и методов, а также
корректность заголовков ``Access-Control-Allow-*`` (§14.12).
"""

from __future__ import annotations

from api_gateway.cors_policy import (
    CorsPolicy,
    is_allowed_origin,
    preflight_headers,
)

_ORIGIN = "https://app.example"
_OTHER = "https://evil.example"


def _policy(
    origins: tuple[str, ...] = (_ORIGIN,),
    *,
    credentials: bool = False,
) -> CorsPolicy:
    """Собрать политику для теста / build a test policy."""
    return CorsPolicy(
        allow_origins=origins,
        allow_methods=("GET", "POST", "OPTIONS"),
        allow_headers=("Authorization", "Content-Type"),
        allow_credentials=credentials,
        max_age=600,
    )


def test_is_allowed_origin_exact_match() -> None:
    """(1) exact-match origin allowed, unlisted origin rejected."""
    policy = _policy()
    assert is_allowed_origin(policy, _ORIGIN) is True
    assert is_allowed_origin(policy, _OTHER) is False


def test_wildcard_matches_any_origin() -> None:
    """(2) ``*`` in allow_origins matches any origin."""
    policy = _policy(origins=("*",))
    assert is_allowed_origin(policy, _ORIGIN) is True
    assert is_allowed_origin(policy, _OTHER) is True
    assert is_allowed_origin(policy, "http://localhost:5173") is True


def test_preflight_disallowed_origin_returns_none() -> None:
    """(3) preflight for a disallowed origin returns None."""
    policy = _policy()
    assert preflight_headers(policy, _OTHER, "GET") is None


def test_preflight_allowed_origin_echoes_origin() -> None:
    """(4) allowed origin+method echoes the origin header."""
    policy = _policy()
    headers = preflight_headers(policy, _ORIGIN, "POST")
    assert headers is not None
    assert headers["Access-Control-Allow-Origin"] == _ORIGIN


def test_preflight_methods_are_comma_joined() -> None:
    """(5) Access-Control-Allow-Methods is the comma-joined methods."""
    policy = _policy()
    headers = preflight_headers(policy, _ORIGIN, "GET")
    assert headers is not None
    value = headers["Access-Control-Allow-Methods"]
    assert value == ", ".join(policy.allow_methods)
    for method in policy.allow_methods:
        assert method in value


def test_preflight_credentials_flag() -> None:
    """(6) allow_credentials True adds the credentials header as 'true'."""
    with_creds = preflight_headers(_policy(credentials=True), _ORIGIN, "GET")
    assert with_creds is not None
    assert with_creds["Access-Control-Allow-Credentials"] == "true"

    without = preflight_headers(_policy(credentials=False), _ORIGIN, "GET")
    assert without is not None
    assert "Access-Control-Allow-Credentials" not in without


def test_preflight_max_age_is_str() -> None:
    """(7) Access-Control-Max-Age equals str(max_age)."""
    policy = _policy()
    headers = preflight_headers(policy, _ORIGIN, "GET")
    assert headers is not None
    assert headers["Access-Control-Max-Age"] == "600"
    assert headers["Access-Control-Max-Age"] == str(policy.max_age)


def test_preflight_disallowed_method_returns_none() -> None:
    """(8) a disallowed request_method returns None."""
    policy = _policy()
    assert preflight_headers(policy, _ORIGIN, "DELETE") is None


def test_preflight_method_case_insensitive() -> None:
    """Method matching is case-insensitive (hand-check of the .upper() path)."""
    policy = _policy()
    headers = preflight_headers(policy, _ORIGIN, "post")
    assert headers is not None
    assert headers["Access-Control-Allow-Origin"] == _ORIGIN


def test_as_dict_round_trip() -> None:
    """as_dict exposes plain fields for logging/assertions."""
    policy = _policy(credentials=True)
    data = policy.as_dict()
    assert data == {
        "allow_origins": [_ORIGIN],
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
        "allow_credentials": True,
        "max_age": 600,
    }
