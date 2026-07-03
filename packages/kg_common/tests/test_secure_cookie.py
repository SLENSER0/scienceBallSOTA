"""Tests for the hardened ``Set-Cookie`` builder (§19.7)."""

from __future__ import annotations

import pytest

from kg_common.security.secure_cookie import (
    CookiePolicy,
    build_set_cookie,
    clear_cookie,
)


def test_default_build_has_http_only() -> None:
    """Assertion (1): default policy build contains ``HttpOnly``."""
    out = build_set_cookie(CookiePolicy(name="rt"), "abc")
    assert "HttpOnly" in out


def test_default_build_has_secure() -> None:
    """Assertion (2): build contains ``Secure``."""
    out = build_set_cookie(CookiePolicy(name="rt"), "abc")
    assert "Secure" in out


def test_default_build_has_same_site_strict() -> None:
    """Assertion (3): build contains ``SameSite=Strict``."""
    out = build_set_cookie(CookiePolicy(name="rt"), "abc")
    assert "SameSite=Strict" in out


def test_max_age_rendered() -> None:
    """Assertion (4): max_age=1209600 renders ``Max-Age=1209600``."""
    out = build_set_cookie(CookiePolicy(name="rt", max_age=1209600), "abc")
    assert "Max-Age=1209600" in out


def test_clear_cookie_expires_with_empty_value() -> None:
    """Assertion (5): clear_cookie has ``Max-Age=0`` and an empty value segment."""
    out = clear_cookie(CookiePolicy(name="rt"))
    assert "Max-Age=0" in out
    assert out.startswith("rt=;")


def test_same_site_none_forces_secure() -> None:
    """Assertion (6): same_site='None' with secure=False still emits ``Secure``."""
    policy = CookiePolicy(name="rt", secure=False, same_site="None")
    out = build_set_cookie(policy, "abc")
    assert "Secure" in out
    assert "SameSite=None" in out


def test_invalid_same_site_raises() -> None:
    """Assertion (7): same_site='Bogus' raises ValueError."""
    with pytest.raises(ValueError):
        build_set_cookie(CookiePolicy(name="rt", same_site="Bogus"), "abc")


def test_build_prefix_and_path() -> None:
    """Assertion (8): output starts with ``name=value`` and includes ``Path=/``."""
    out = build_set_cookie(CookiePolicy(name="name"), "value")
    assert out.startswith("name=value")
    assert "Path=/" in out


def test_domain_included_when_set() -> None:
    """A domain attribute appears only when configured («домен опционален»)."""
    with_domain = build_set_cookie(CookiePolicy(name="rt", domain="example.org"), "abc")
    without_domain = build_set_cookie(CookiePolicy(name="rt"), "abc")
    assert "Domain=example.org" in with_domain
    assert "Domain=" not in without_domain


def test_lax_same_site_without_secure() -> None:
    """A non-``None`` SameSite does not force Secure when disabled («без Secure»)."""
    out = build_set_cookie(CookiePolicy(name="rt", secure=False, same_site="Lax"), "abc")
    assert "Secure" not in out
    assert "SameSite=Lax" in out


def test_as_dict_roundtrip() -> None:
    """``as_dict`` exposes every attribute («сериализация политики»)."""
    policy = CookiePolicy(name="rt", max_age=60, domain="d")
    data = policy.as_dict()
    assert data["name"] == "rt"
    assert data["max_age"] == 60
    assert data["domain"] == "d"
    assert data["same_site"] == "Strict"
