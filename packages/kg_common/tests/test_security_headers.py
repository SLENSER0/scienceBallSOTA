"""Tests for the HTTP security headers builder — тесты построителя заголовков (§19.7)."""

from __future__ import annotations

import pytest

from kg_common.security.security_headers import SecurityHeaderPolicy, build_headers


def test_default_headers_present() -> None:
    h = build_headers(SecurityHeaderPolicy())
    assert h["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert h["X-Frame-Options"] == "DENY"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in h
    assert h["Content-Security-Policy"] == "default-src 'self'"
    assert h["Referrer-Policy"] == "no-referrer"


def test_disable_hsts_omits_header() -> None:
    h = build_headers(SecurityHeaderPolicy(enable_hsts=False))
    assert "Strict-Transport-Security" not in h
    # Остальные заголовки остаются на месте.
    assert h["X-Frame-Options"] == "DENY"


def test_custom_frame_options() -> None:
    h = build_headers(SecurityHeaderPolicy(frame_options="SAMEORIGIN"))
    assert h["X-Frame-Options"] == "SAMEORIGIN"


def test_custom_hsts_max_age() -> None:
    h = build_headers(SecurityHeaderPolicy(hsts_max_age=600))
    assert h["Strict-Transport-Security"] == "max-age=600; includeSubDomains"


def test_disable_content_type_options() -> None:
    h = build_headers(SecurityHeaderPolicy(content_type_options=False))
    assert "X-Content-Type-Options" not in h


def test_custom_csp_and_referrer() -> None:
    policy = SecurityHeaderPolicy(csp="default-src 'none'", referrer_policy="origin")
    h = build_headers(policy)
    assert h["Content-Security-Policy"] == "default-src 'none'"
    assert h["Referrer-Policy"] == "origin"


def test_as_dict_roundtrip() -> None:
    d = SecurityHeaderPolicy().as_dict()
    assert d["hsts_max_age"] == 31536000
    assert d["enable_hsts"] is True
    assert d["frame_options"] == "DENY"
    assert d["content_type_options"] is True
    assert d["csp"] == "default-src 'self'"
    assert d["referrer_policy"] == "no-referrer"


def test_policy_is_frozen() -> None:
    policy = SecurityHeaderPolicy()
    with pytest.raises((AttributeError, TypeError)):
        policy.frame_options = "SAMEORIGIN"  # type: ignore[misc]
