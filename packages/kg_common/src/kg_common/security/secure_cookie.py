"""Hardened ``Set-Cookie`` builder for the refresh-token cookie flow (§19.7).

Transport hardening for the cookie-based refresh flow («поток обновления через
cookie»): this module assembles a single hardened ``Set-Cookie`` header value
with the security attributes ``HttpOnly``, ``Secure`` and ``SameSite``. It
complements :mod:`kg_common.security.csrf` (double-submit tokens), which signs
and verifies the CSRF token but does *not* emit the cookie itself.

:class:`CookiePolicy` is a frozen dataclass describing one cookie's attributes.
:func:`build_set_cookie` serializes a ``name=value`` pair followed by ``Path``,
``Domain``, ``Max-Age``, ``Secure``, ``HttpOnly`` and ``SameSite`` attributes;
it validates ``same_site`` against the RFC 6265bis set ``{Strict, Lax, None}``
and forces ``Secure`` when ``SameSite=None`` (a hard requirement of modern
browsers). :func:`clear_cookie` emits an expiring cookie («сброс cookie») with
an empty value and ``Max-Age=0``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Allowed ``SameSite`` values per RFC 6265bis («допустимые значения SameSite»).
_SAME_SITE_VALUES = frozenset({"Strict", "Lax", "None"})


@dataclass(frozen=True)
class CookiePolicy:
    """Immutable cookie attribute policy («политика cookie»).

    :param name: cookie name (the key of the ``name=value`` pair).
    :param http_only: emit ``HttpOnly`` (blocks JS access to the cookie).
    :param secure: emit ``Secure`` (cookie only sent over TLS).
    :param same_site: one of ``Strict``/``Lax``/``None`` (cross-site policy).
    :param path: ``Path`` attribute scope.
    :param domain: optional ``Domain`` attribute; omitted when ``None``.
    :param max_age: optional ``Max-Age`` in seconds; omitted when ``None``.
    """

    name: str
    http_only: bool = True
    secure: bool = True
    same_site: str = "Strict"
    path: str = "/"
    domain: str | None = None
    max_age: int | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a log-safe view of the policy («представление для логов»)."""
        return {
            "name": self.name,
            "http_only": self.http_only,
            "secure": self.secure,
            "same_site": self.same_site,
            "path": self.path,
            "domain": self.domain,
            "max_age": self.max_age,
        }


def _assemble(
    policy: CookiePolicy,
    value: str,
    *,
    max_age: int | None,
) -> str:
    """Assemble the ``Set-Cookie`` value for *policy* with an explicit *max_age*.

    Validates ``same_site`` and forces ``Secure`` when ``SameSite=None`` per
    RFC 6265bis. Attribute order: ``name=value`` then ``Path``, ``Domain``,
    ``Max-Age``, ``Secure``, ``HttpOnly``, ``SameSite``.
    """
    if policy.same_site not in _SAME_SITE_VALUES:
        allowed = ", ".join(sorted(_SAME_SITE_VALUES))
        raise ValueError(f"invalid same_site {policy.same_site!r}; expected one of {allowed}")

    # ``SameSite=None`` is only honored on a Secure cookie («принудительный Secure»).
    secure = policy.secure or policy.same_site == "None"

    parts = [f"{policy.name}={value}"]
    parts.append(f"Path={policy.path}")
    if policy.domain is not None:
        parts.append(f"Domain={policy.domain}")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if secure:
        parts.append("Secure")
    if policy.http_only:
        parts.append("HttpOnly")
    parts.append(f"SameSite={policy.same_site}")
    return "; ".join(parts)


def build_set_cookie(policy: CookiePolicy, value: str) -> str:
    """Build a hardened ``Set-Cookie`` header value for *policy* (§19.7).

    Raises :class:`ValueError` if ``policy.same_site`` is not one of
    ``Strict``/``Lax``/``None``. When ``same_site == 'None'`` the ``Secure``
    attribute is emitted regardless of ``policy.secure``.
    """
    return _assemble(policy, value, max_age=policy.max_age)


def clear_cookie(policy: CookiePolicy) -> str:
    """Build an expiring ``Set-Cookie`` that clears the cookie (§19.7).

    Emits an empty value and ``Max-Age=0`` («сброс cookie») so the browser
    deletes the cookie immediately, preserving the other hardening attributes.
    """
    return _assemble(policy, "", max_age=0)
