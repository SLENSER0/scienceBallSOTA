"""Tests for inbound caller-IP allowlist classification (§19.7 transport)."""

from __future__ import annotations

from kg_common.security.ip_allowlist import (
    IpAllowPolicy,
    IpDecision,
    classify_ip,
    ip_allowed,
)


def test_allow_cidr_matches_ipv4() -> None:
    """An IP inside an allow-CIDR is admitted with reason ``allow`` and the CIDR."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",))
    decision = classify_ip(policy, "10.0.0.5")
    assert decision.allowed is True
    assert decision.reason == "allow"
    assert decision.matched_cidr == "10.0.0.0/8"


def test_deny_precedence_over_allow() -> None:
    """A denied subnet nested inside an allowed range is refused — deny wins."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",), deny_cidrs=("10.0.0.0/16",))
    decision = classify_ip(policy, "10.0.0.5")
    assert decision.allowed is False
    assert decision.reason == "deny"
    assert decision.matched_cidr == "10.0.0.0/16"


def test_default_deny_when_no_match() -> None:
    """An unmatched IP under the default policy is refused with ``default_deny``."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",), default_allow=False)
    decision = classify_ip(policy, "8.8.8.8")
    assert decision.allowed is False
    assert decision.reason == "default_deny"
    assert decision.matched_cidr is None


def test_default_allow_when_no_match() -> None:
    """An unmatched IP with ``default_allow`` is admitted with ``default_allow``."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",), default_allow=True)
    decision = classify_ip(policy, "8.8.8.8")
    assert decision.allowed is True
    assert decision.reason == "default_allow"
    assert decision.matched_cidr is None


def test_invalid_ip_denied() -> None:
    """Unparseable input is refused with reason ``invalid`` and no matched CIDR."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",), default_allow=True)
    decision = classify_ip(policy, "not-an-ip")
    assert decision.allowed is False
    assert decision.reason == "invalid"
    assert decision.matched_cidr is None


def test_allow_cidr_matches_ipv6() -> None:
    """An IPv6 address inside an IPv6 allow-CIDR is admitted."""
    policy = IpAllowPolicy(allow_cidrs=("2001:db8::/32",))
    decision = classify_ip(policy, "2001:db8::1")
    assert decision.allowed is True
    assert decision.reason == "allow"
    assert decision.matched_cidr == "2001:db8::/32"


def test_ipv4_never_matches_ipv6_network() -> None:
    """A version mismatch does not match: an IPv4 IP against an IPv6 allow-CIDR."""
    policy = IpAllowPolicy(allow_cidrs=("2001:db8::/32",))
    decision = classify_ip(policy, "10.0.0.5")
    assert decision.allowed is False
    assert decision.reason == "default_deny"


def test_ip_allowed_matches_classify() -> None:
    """``ip_allowed`` returns the same boolean as ``classify_ip(...).allowed``."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",), deny_cidrs=("10.0.0.0/16",))
    for ip in ("10.0.0.5", "10.1.0.5", "8.8.8.8", "not-an-ip"):
        assert ip_allowed(policy, ip) == classify_ip(policy, ip).allowed


def test_decision_as_dict_round_trip() -> None:
    """:meth:`IpDecision.as_dict` round-trips reason and matched_cidr."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",))
    decision = classify_ip(policy, "10.0.0.5")
    assert decision.as_dict() == {
        "ip": "10.0.0.5",
        "allowed": True,
        "matched_cidr": "10.0.0.0/8",
        "reason": "allow",
    }


def test_policy_as_dict() -> None:
    """:meth:`IpAllowPolicy.as_dict` exposes all three configuration fields."""
    policy = IpAllowPolicy(allow_cidrs=("10.0.0.0/8",), deny_cidrs=("10.0.0.0/16",))
    assert policy.as_dict() == {
        "allow_cidrs": ["10.0.0.0/8"],
        "deny_cidrs": ["10.0.0.0/16"],
        "default_allow": False,
    }


def test_invalid_decision_direct_as_dict() -> None:
    """An ``invalid`` decision serializes with a null matched_cidr."""
    decision = IpDecision(ip="x", allowed=False, matched_cidr=None, reason="invalid")
    assert decision.as_dict()["matched_cidr"] is None
    assert decision.as_dict()["reason"] == "invalid"
