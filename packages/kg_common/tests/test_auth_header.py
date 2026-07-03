"""Tests for Authorization-header parsing/classification (§19.2 auth)."""

from __future__ import annotations

from kg_common.security.auth_header import (
    AuthToken,
    classify_credential,
    parse_authorization,
    stream_token_from_query,
)


def test_bearer_jwt_kind() -> None:
    """A three-segment base64url Bearer credential is classified as a JWT."""
    tok = parse_authorization("Bearer eyJh.eyJb.sig")
    assert tok is not None
    assert tok.kind == "jwt"
    assert tok.scheme == "Bearer"
    assert tok.credential == "eyJh.eyJb.sig"


def test_bearer_api_key_kind() -> None:
    """An ``sk_``-prefixed Bearer credential is classified as an API key."""
    tok = parse_authorization("Bearer sk_live_123")
    assert tok is not None
    assert tok.kind == "api_key"


def test_lowercase_bearer_scheme_normalized() -> None:
    """A lowercase ``bearer`` scheme normalizes to ``Bearer`` and still classifies."""
    tok = parse_authorization("bearer sk_x")
    assert tok is not None
    assert tok.scheme == "Bearer"
    assert tok.kind == "api_key"


def test_none_header_returns_none() -> None:
    """A missing header yields ``None``."""
    assert parse_authorization(None) is None


def test_basic_scheme_unknown_kind() -> None:
    """A non-Bearer scheme keeps its name and is never classified beyond unknown."""
    tok = parse_authorization("Basic abc")
    assert tok is not None
    assert tok.scheme == "Basic"
    assert tok.kind == "unknown"


def test_bearer_without_credential_returns_none() -> None:
    """A lone scheme with no credential yields ``None``."""
    assert parse_authorization("Bearer") is None


def test_classify_credential_api_key() -> None:
    """A bare ``sk_``-prefixed string classifies directly as an API key."""
    assert classify_credential("sk_abc") == "api_key"


def test_stream_token_from_query() -> None:
    """The ``token`` query value is returned; an empty mapping yields ``None``."""
    assert stream_token_from_query({"token": "t1"}) == "t1"
    assert stream_token_from_query({}) is None


def test_classify_credential_jwt_and_unknown() -> None:
    """Three base64url segments are a JWT; a plain word is unknown."""
    assert classify_credential("aaa.bbb.ccc") == "jwt"
    assert classify_credential("plaintext") == "unknown"
    # An empty middle segment is not a valid base64url JWT segment.
    assert classify_credential("aaa..ccc") == "unknown"


def test_as_dict_round_trip() -> None:
    """:meth:`AuthToken.as_dict` exposes all three fields for logging."""
    tok = AuthToken(scheme="Bearer", kind="jwt", credential="a.b.c")
    assert tok.as_dict() == {"scheme": "Bearer", "kind": "jwt", "credential": "a.b.c"}


def test_blank_header_returns_none() -> None:
    """A whitespace-only header yields ``None``."""
    assert parse_authorization("   ") is None
