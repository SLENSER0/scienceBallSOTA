"""Tests for the SSRF guard — тесты защиты от SSRF (§19.7)."""

from __future__ import annotations

import pytest

from kg_common.security.ssrf_guard import SsrfPolicy, UrlVerdict, classify_url


def test_public_https_allowed() -> None:
    v = classify_url("https://example.com/x", SsrfPolicy())
    assert v.allowed is True
    assert v.reason == "ok"


def test_metadata_host_blocked() -> None:
    v = classify_url("http://169.254.169.254/latest", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "metadata"


def test_private_ipv4_blocked() -> None:
    v = classify_url("https://10.0.0.5/", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "private"


def test_disallowed_scheme() -> None:
    v = classify_url("ftp://example.com", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "scheme"


def test_loopback_ipv4_blocked() -> None:
    assert classify_url("https://127.0.0.1/", SsrfPolicy()).allowed is False
    assert classify_url("https://127.0.0.1/", SsrfPolicy()).reason == "private"


def test_loopback_ipv6_blocked() -> None:
    v = classify_url("https://[::1]/", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "private"


def test_extra_blocked_host() -> None:
    policy = SsrfPolicy(extra_blocked_hosts=frozenset({"internal.svc"}))
    v = classify_url("https://internal.svc/", policy)
    assert v.allowed is False
    assert v.reason == "blocked_host"


def test_extra_blocked_host_not_matched_for_others() -> None:
    policy = SsrfPolicy(extra_blocked_hosts=frozenset({"internal.svc"}))
    assert classify_url("https://example.com/", policy).allowed is True


def test_link_local_ipv4_private() -> None:
    # A non-metadata link-local address is still rejected as private.
    v = classify_url("https://169.254.10.20/", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "private"


def test_reserved_and_unspecified_blocked() -> None:
    assert classify_url("https://0.0.0.0/", SsrfPolicy()).reason == "private"
    assert classify_url("https://192.168.1.1/", SsrfPolicy()).reason == "private"
    assert classify_url("https://172.16.5.5/", SsrfPolicy()).reason == "private"


def test_ipv6_private_blocked() -> None:
    v = classify_url("https://[fd00::1]/", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "private"


def test_scheme_checked_before_host() -> None:
    # ftp to a private IP is rejected on scheme first (deny-by-default order).
    v = classify_url("ftp://10.0.0.1/", SsrfPolicy())
    assert v.reason == "scheme"


def test_scheme_is_case_insensitive() -> None:
    assert classify_url("HTTPS://example.com/", SsrfPolicy()).allowed is True


def test_block_private_disabled() -> None:
    policy = SsrfPolicy(block_private=False)
    v = classify_url("https://10.0.0.5/", policy)
    assert v.allowed is True
    assert v.reason == "ok"


def test_block_metadata_disabled_falls_through_to_private() -> None:
    # Metadata IP is link-local, so with metadata off it is still private.
    policy = SsrfPolicy(block_metadata=False)
    v = classify_url("http://169.254.169.254/latest", policy)
    assert v.allowed is False
    assert v.reason == "private"


def test_metadata_and_private_both_off_allows() -> None:
    policy = SsrfPolicy(block_metadata=False, block_private=False)
    v = classify_url("http://169.254.169.254/latest", policy)
    assert v.allowed is True


def test_empty_host_blocked() -> None:
    v = classify_url("https:///path", SsrfPolicy())
    assert v.allowed is False
    assert v.reason == "blocked_host"


def test_url_verdict_as_dict_round_trips() -> None:
    v = UrlVerdict("https://example.com/", True, "ok")
    d = v.as_dict()
    assert d == {"url": "https://example.com/", "allowed": True, "reason": "ok"}
    assert set(d.keys()) == {"url", "allowed", "reason"}


def test_policy_as_dict_keys() -> None:
    d = SsrfPolicy(extra_blocked_hosts=frozenset({"a.b"})).as_dict()
    assert d["allowed_schemes"] == ["http", "https"]
    assert d["block_private"] is True
    assert d["block_metadata"] is True
    assert d["extra_blocked_hosts"] == ["a.b"]


def test_policy_defaults() -> None:
    p = SsrfPolicy()
    assert p.allowed_schemes == frozenset({"http", "https"})
    assert p.block_private is True
    assert p.block_metadata is True
    assert p.extra_blocked_hosts == frozenset()


def test_policy_is_frozen() -> None:
    p = SsrfPolicy()
    with pytest.raises(AttributeError):
        p.block_private = False  # type: ignore[misc]


def test_verdict_is_frozen() -> None:
    v = UrlVerdict("u", True, "ok")
    with pytest.raises(AttributeError):
        v.allowed = False  # type: ignore[misc]
