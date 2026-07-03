"""Inbound caller-IP allowlist for admin/ops endpoints (§19.7 transport hardening).

Admin and ops endpoints must only answer callers from trusted networks. An
:class:`IpAllowPolicy` declares ``allow_cidrs`` (networks that may reach the
endpoint) and ``deny_cidrs`` (networks that are refused even if they also match
an allow rule). The policy is **deny-by-default** («по умолчанию запрет»): a
caller whose IP matches nothing is refused unless ``default_allow`` is set.

:func:`classify_ip` parses the caller IP with the stdlib :mod:`ipaddress` module
(IPv4 or IPv6) and returns an :class:`IpDecision`; :func:`ip_allowed` is the
boolean shorthand. **Deny wins** — deny-CIDRs are checked before allow-CIDRs, so
a blocked subnet inside a broader allowed range is still refused. Unparseable
input is denied with reason ``'invalid'`` («нераспознанный адрес — отказ»).

This classifies **inbound** caller IPs and is deliberately distinct from
:mod:`kg_common.security.ssrf_guard`, which classifies **outbound** fetch URLs.
Pure-python, stdlib only — no third-party dependency.

Reasons: ``'deny'`` | ``'allow'`` | ``'default_deny'`` | ``'default_allow'`` |
``'invalid'``.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IpAllowPolicy:
    """Immutable inbound-IP allowlist policy (§19.7).

    :param allow_cidrs: CIDR networks whose callers are admitted («разрешённые сети»).
    :param deny_cidrs: CIDR networks refused even if also allowed — deny wins.
    :param default_allow: verdict for an IP matching neither list (default deny).
    """

    allow_cidrs: tuple[str, ...]
    deny_cidrs: tuple[str, ...] = ()
    default_allow: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this policy («сериализация политики»)."""
        return {
            "allow_cidrs": list(self.allow_cidrs),
            "deny_cidrs": list(self.deny_cidrs),
            "default_allow": self.default_allow,
        }


@dataclass(frozen=True)
class IpDecision:
    """Outcome of classifying one caller IP («вердикт по одному адресу»).

    :param ip: the caller IP as supplied.
    :param allowed: whether the caller is admitted.
    :param matched_cidr: the CIDR that decided the verdict, or ``None``.
    :param reason: one of ``deny`` / ``allow`` / ``default_deny`` /
        ``default_allow`` / ``invalid``.
    """

    ip: str
    allowed: bool
    matched_cidr: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of the decision («словарь для сериализации»)."""
        return {
            "ip": self.ip,
            "allowed": self.allowed,
            "matched_cidr": self.matched_cidr,
            "reason": self.reason,
        }


def _first_match(addr: ipaddress._BaseAddress, cidrs: tuple[str, ...]) -> str | None:
    """Return the first CIDR in *cidrs* that contains *addr*, else ``None``.

    Malformed or version-mismatched CIDRs are skipped, never raised («игнорируем
    некорректные сети»): an IPv4 address never matches an IPv6 network.
    """
    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if addr.version == network.version and addr in network:
            return cidr
    return None


def classify_ip(policy: IpAllowPolicy, ip: str) -> IpDecision:
    """Classify caller *ip* against *policy*, returning an :class:`IpDecision` (§19.7).

    Order: parse the IP (invalid → refused) → deny-CIDRs (deny wins) → allow-CIDRs
    → the ``default_allow`` fallback. Deny always precedes allow, so a denied
    subnet nested inside an allowed range is still refused («запрет важнее»).
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return IpDecision(ip=ip, allowed=False, matched_cidr=None, reason="invalid")

    denied = _first_match(addr, policy.deny_cidrs)
    if denied is not None:
        return IpDecision(ip=ip, allowed=False, matched_cidr=denied, reason="deny")

    allowed = _first_match(addr, policy.allow_cidrs)
    if allowed is not None:
        return IpDecision(ip=ip, allowed=True, matched_cidr=allowed, reason="allow")

    if policy.default_allow:
        return IpDecision(ip=ip, allowed=True, matched_cidr=None, reason="default_allow")
    return IpDecision(ip=ip, allowed=False, matched_cidr=None, reason="default_deny")


def ip_allowed(policy: IpAllowPolicy, ip: str) -> bool:
    """Return whether caller *ip* is admitted by *policy* («разрешён ли адрес»).

    Boolean shorthand equal to ``classify_ip(policy, ip).allowed``.
    """
    return classify_ip(policy, ip).allowed
