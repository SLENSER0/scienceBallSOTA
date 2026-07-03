"""Content-Security-Policy directive builder with nonce support (§19.7).

Composes a valid ``Content-Security-Policy`` header string from *structured*
directives, replacing the single opaque ``csp`` string of ``security_headers``
with a composable, nonce-aware builder. Директивы CSP собираются из структуры.

A frozen :class:`CspPolicy` maps directive names to source tuples. :func:`build_csp`
emits directives sorted alphabetically as ``name src src`` joined by ``'; '``,
optionally injecting a per-request ``'nonce-<nonce>'`` source into ``script-src``
and ``style-src``, and appending ``upgrade-insecure-requests`` / ``report-uri``.
Замороженная политика и функция сборки строки заголовка CSP. Pure-python.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# Directives that receive a per-request nonce source («директивы с nonce»).
_NONCE_TARGETS: tuple[str, ...] = ("script-src", "style-src")


@dataclass(frozen=True)
class CspPolicy:
    """Immutable Content-Security-Policy definition — неизменяемая политика CSP (§19.7).

    Attributes:
        directives: Directive name → source tuple — имя директивы к кортежу источников.
        report_uri: Optional ``report-uri`` target — необязательный адрес отчётов.
        upgrade_insecure: Append ``upgrade-insecure-requests`` — обновлять http→https.
    """

    directives: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    report_uri: str | None = None
    upgrade_insecure: bool = False

    def as_dict(self) -> dict[str, object]:
        """Return the policy as a plain dict — вернуть политику как словарь (§19.7)."""
        return {
            "directives": {name: tuple(src) for name, src in self.directives.items()},
            "report_uri": self.report_uri,
            "upgrade_insecure": self.upgrade_insecure,
        }


def default_policy() -> CspPolicy:
    """Return a self-only baseline policy — базовая политика «только self» (§19.7)."""
    return CspPolicy(
        directives={
            "default-src": ("'self'",),
            "script-src": ("'self'",),
            "style-src": ("'self'",),
        }
    )


def with_nonce(policy: CspPolicy, nonce: str) -> CspPolicy:
    """Return a copy with a nonce source injected — копия с внедрённым nonce (§19.7).

    A ``'nonce-<nonce>'`` source is appended to ``script-src`` and ``style-src``
    (creating either directive if absent). The original policy is left unchanged.

    Args:
        policy: Source policy to derive from — исходная политика.
        nonce: Opaque per-request nonce value — одноразовое значение запроса.

    Returns:
        A new :class:`CspPolicy` with the nonce injected — новая политика с nonce.
    """
    token = f"'nonce-{nonce}'"
    merged: dict[str, tuple[str, ...]] = {
        name: tuple(src) for name, src in policy.directives.items()
    }
    for target in _NONCE_TARGETS:
        existing = merged.get(target, ())
        if token not in existing:
            merged[target] = (*existing, token)
    return CspPolicy(
        directives=merged,
        report_uri=policy.report_uri,
        upgrade_insecure=policy.upgrade_insecure,
    )


def build_csp(policy: CspPolicy, nonce: str | None = None) -> str:
    """Build a ``Content-Security-Policy`` header value — собрать значение CSP (§19.7).

    Directives are emitted sorted by name as ``name src src`` joined by ``'; '``;
    directives with an empty source tuple are omitted. When ``nonce`` is given a
    ``'nonce-<nonce>'`` source is injected into ``script-src`` and ``style-src``.
    ``upgrade-insecure-requests`` and ``report-uri <uri>`` are appended when set.

    Args:
        policy: Source CSP policy — исходная политика CSP.
        nonce: Optional per-request nonce — необязательный одноразовый nonce.

    Returns:
        The header value string — строка значения заголовка.
    """
    effective = with_nonce(policy, nonce) if nonce is not None else policy
    parts: list[str] = []
    for name in sorted(effective.directives):
        sources = tuple(effective.directives[name])
        if not sources:
            continue
        parts.append(" ".join((name, *sources)))
    if effective.upgrade_insecure:
        parts.append("upgrade-insecure-requests")
    if effective.report_uri is not None:
        parts.append(f"report-uri {effective.report_uri}")
    return "; ".join(parts)
