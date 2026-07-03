"""SSRF guard for ingestion fetch — защита от SSRF при загрузке (§19.7).

Before the ingestion pipeline fetches a remote URL we classify it against an
:class:`SsrfPolicy` so an attacker cannot coerce the server into requesting
internal or cloud-metadata endpoints («запрос к внутренним адресам запрещён»).
:func:`classify_url` parses the URL, and for **literal IP** hosts uses
:mod:`ipaddress` to reject private / loopback / link-local / reserved ranges and
the cloud-metadata address ``169.254.169.254``. The policy is deny-by-default:
only ``http`` / ``https`` schemes to a non-blocked, non-private host are allowed.
No DNS resolution is performed here (hostnames are not resolved) — pure-python,
stdlib only, no third-party dependency.

Reasons: ``'scheme'`` | ``'private'`` | ``'metadata'`` | ``'blocked_host'`` |
``'ok'``.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

# Cloud-metadata service address («адрес сервиса метаданных») — link-local IMDS.
_METADATA_HOST = "169.254.169.254"


@dataclass(frozen=True)
class SsrfPolicy:
    """Policy governing which fetch URLs are permitted («политика допуска URL»).

    :param allowed_schemes: URL schemes that may ever be fetched (default http/https).
    :param block_private: reject literal private/loopback/link-local/reserved IPs.
    :param block_metadata: reject the cloud-metadata host ``169.254.169.254``.
    :param extra_blocked_hosts: additional exact hostnames to deny (deny-by-default).
    """

    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    block_private: bool = True
    block_metadata: bool = True
    extra_blocked_hosts: frozenset[str] = field(default_factory=frozenset)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this policy («сериализация политики»)."""
        return {
            "allowed_schemes": sorted(self.allowed_schemes),
            "block_private": self.block_private,
            "block_metadata": self.block_metadata,
            "extra_blocked_hosts": sorted(self.extra_blocked_hosts),
        }


@dataclass(frozen=True)
class UrlVerdict:
    """Outcome of classifying one URL («вердикт по одному URL»)."""

    url: str
    allowed: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping with keys ``url`` / ``allowed`` / ``reason``."""
        return {"url": self.url, "allowed": self.allowed, "reason": self.reason}


def _parse_ip(host: str) -> ipaddress._BaseAddress | None:
    """Return the parsed IP if *host* is a literal address, else ``None``.

    A hostname (``example.com``) is not an IP literal and yields ``None`` — we do
    not resolve DNS here («DNS не резолвим»).
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    """True if *ip* falls in a private / loopback / link-local / reserved range."""
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    )


def classify_url(raw_url: str, policy: SsrfPolicy) -> UrlVerdict:
    """Classify *raw_url* against *policy*, returning a :class:`UrlVerdict` (§19.7).

    Checks in order: scheme → explicit blocked host → cloud-metadata host →
    private/loopback/link-local/reserved IP. The default is to allow only a
    valid ``http``/``https`` URL to a public host («по умолчанию — запрет»).
    """
    parts = urlsplit(raw_url)
    scheme = parts.scheme.lower()
    if scheme not in policy.allowed_schemes:
        return UrlVerdict(raw_url, False, "scheme")

    host = (parts.hostname or "").lower()
    if not host:
        return UrlVerdict(raw_url, False, "blocked_host")

    if host in policy.extra_blocked_hosts:
        return UrlVerdict(raw_url, False, "blocked_host")

    ip = _parse_ip(host)
    if ip is not None:
        if policy.block_metadata and host == _METADATA_HOST:
            return UrlVerdict(raw_url, False, "metadata")
        if policy.block_private and _is_blocked_ip(ip):
            return UrlVerdict(raw_url, False, "private")

    return UrlVerdict(raw_url, True, "ok")
